"""Scheduled reports by email: the diffusions, stored in DB (like SMTP/general).

A diffusion is one scheduled mailing: a scope, a calendar, the documents its
mails carry and who receives them. There can be as many as needed, several for
the same tribe (the leaders on Monday, a committee on Friday). Each is stored in
``app_settings['report_diffusion:<id>']`` and sent by
report.send_due_weekly_reports.

Two scopes, same calendar fields:

  * the Direction (``tribe_id`` None, admin only): the whole document, every
    tribe, to the people and addresses named (``copies``);
  * a tribe (``tribe_id``, set by the admin or by that tribe's leader): the tribe
    leader is the main recipient and gets the tribe's mail (``leader_tribe``),
    one mail per squad (``leader_squads``), or both; the squads' people are added
    by role (leader, co-leaders, contributors); others by persona, by name or by
    address (``copies``), each with what it gets: the tribe's document, or the
    mails of the chosen squads.

Who receives what is computed in app/mailplan.py. The settings of the earlier
shapes (one schedule per tribe and one for the Direction, keys ``weekly_report``
and ``weekly_report:tribe:<id>``) are converted once into diffusions by
``ensure_diffusions``.
"""
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import AppSetting

PREFIX = "report_diffusion:"
COPY_TYPES = ("persona", "user", "email")
COPY_CONTENTS = ("tribe", "squads")
MAX_COPIES = 50
MAX_NAME = 80
# The documents a mail can carry, as PowerPoint attachments: the weekly report
# (whose summary is also the mail's body), the dashboard, the roadmap and the
# dependencies. Chosen per kind of mail: the Direction's ("all"), a tribe's
# document ("tribe") and the squad mails ("squad").
DOC_TYPES = ("weekly", "dashboard", "roadmap", "dependencies")
# The blocks of a mail's body, in the order they appear (mailbody.render_email).
# "squads" (the table of squads) only applies to a tribe or a whole-scope mail.
BODY_SECTIONS = ("changes", "kpis", "squads", "key_messages", "late_otds", "kpi_watch", "milestones")
# What a mail held before the body could be chosen: a diffusion without "body" keeps it.
DEFAULT_BODY = {"tribe": ["changes", "kpis", "squads"], "all": ["changes", "kpis", "squads"],
                "squad": ["changes", "kpis", "key_messages", "late_otds", "kpi_watch", "milestones"]}
# Scheduler bookkeeping: never taken from a screen.
BOOKKEEPING = ("last_sent_day", "last_sent_week", "v", "id")


def key_of(diffusion_id: int) -> str:
    return f"{PREFIX}{int(diffusion_id)}"


def defaults(tribe_id: int | None) -> dict:
    """A new diffusion of a scope: paused, Monday 8 h, the weekly report."""
    cfg = {
        "id": None,
        "name": "",
        "tribe_id": tribe_id,
        "enabled": False,
        # Days of the week to send on (0 = Monday ... 6 = Sunday), Paris time.
        "weekdays": [0],
        "hour": 8,
        # Minutes past the hour, by 5 (the scheduler ticks every 5 minutes).
        "minute": 0,
        # Look-back window of the "what's new" section.
        "since_days": 7,
        # Each mail goes out only when ITS document changed since it was last sent.
        "only_when_changes": False,
        # Bookkeeping: ISO date already sent today (per-day idempotency).
        "last_sent_day": "",
        # Other recipients: {"type": persona|user|email, "value", "content": tribe|squads, "squad_ids"}.
        "copies": [],
    }
    if tribe_id is None:
        cfg["docs"] = {"all": ["weekly"]}
        cfg["body"] = {"all": list(BODY_SECTIONS)}
    else:
        cfg.update({
            # What the tribe leader receives: the tribe's mail, one mail per squad, or both.
            "leader_tribe": True,
            "leader_squads": False,
            # The squads the squad mails cover (empty = every squad of the tribe).
            "squad_ids": [],
            # The squads' people, by role.
            "copy_leader": False,
            "copy_co_leaders": False,
            "copy_contributors": False,
            "docs": {"tribe": ["weekly"], "squad": ["weekly"]},
            "body": {"tribe": list(BODY_SECTIONS), "squad": [b for b in BODY_SECTIONS if b != "squads"]},
        })
    return cfg


def _parse(raw: str | None) -> dict | None:
    try:
        out = json.loads(raw or "")
        return out if isinstance(out, dict) else None
    except (json.JSONDecodeError, TypeError):
        return None


def _from_row(row: AppSetting) -> dict | None:
    stored = _parse(row.value)
    if stored is None:
        return None
    try:
        did = int(row.key[len(PREFIX):])
    except ValueError:
        return None
    tid = stored.get("tribe_id")
    cfg = defaults(int(tid) if tid is not None else None)
    cfg.update({k: v for k, v in stored.items() if k in cfg})
    if "body" not in stored:
        # Saved before the content could be chosen: its mails keep what they held.
        cfg["body"] = {k: list(DEFAULT_BODY[k]) for k in cfg["docs"]}
    cfg["id"] = did
    return cfg


def get_diffusion(db: Session, diffusion_id: int) -> dict | None:
    row = db.get(AppSetting, key_of(diffusion_id))
    return _from_row(row) if row else None


def list_diffusions(db: Session, tribe_id: int | None = None, *, every: bool = True) -> list[dict]:
    """Every diffusion (``every``), or those of one scope (``tribe_id``, None =
    the Direction's), by id."""
    rows = db.scalars(select(AppSetting).where(AppSetting.key.like(PREFIX + "%"))).all()
    out = [c for c in (_from_row(r) for r in rows) if c is not None]
    if not every:
        out = [c for c in out if c["tribe_id"] == tribe_id]
    return sorted(out, key=lambda c: c["id"])


def _next_id(db: Session) -> int:
    keys = db.scalars(select(AppSetting.key).where(AppSetting.key.like(PREFIX + "%"))).all()
    ids = []
    for k in keys:
        try:
            ids.append(int(k[len(PREFIX):]))
        except ValueError:
            continue
    return max(ids, default=0) + 1


def _clean_weekdays(value) -> list[int]:
    """Coerce to a sorted, de-duplicated list of valid weekday ints (0=Mon..6=Sun).
    Non-int and out-of-range entries are dropped; empty result defaults to [0]."""
    out = []
    for x in value or []:
        try:
            d = int(x)
        except (TypeError, ValueError):
            continue
        if 0 <= d <= 6:
            out.append(d)
    return sorted(set(out)) or [0]


def _ints(value) -> list[int]:
    out = []
    for x in value or []:
        try:
            out.append(int(x))
        except (TypeError, ValueError):
            continue
    return sorted(set(out))


def _clean_recipients(value) -> list[str]:
    """Normalize recipients (list or comma/semicolon/newline string) to unique
    addresses. Keeps only entries containing '@', de-duplicated case-insensitively
    while preserving original casing and order."""
    if isinstance(value, str):
        parts = value.replace(",", "\n").replace(";", "\n").splitlines()
    elif isinstance(value, list):
        parts = value
    else:
        return []
    seen, out = set(), []
    for p in parts:
        addr = str(p).strip()
        if addr and "@" in addr and addr.lower() not in seen:
            seen.add(addr.lower())
            out.append(addr)
    return out


def _clean_copies(value, direction: bool) -> list[dict]:
    """Keep the well-formed copies, once each (same type and value). The
    Direction's always get the whole document."""
    out, seen = [], set()
    for c in value if isinstance(value, list) else []:
        if not isinstance(c, dict) or c.get("type") not in COPY_TYPES:
            continue
        kind, raw = c["type"], c.get("value")
        if kind == "user":
            try:
                val = int(raw)
            except (TypeError, ValueError):
                continue
        else:
            val = str(raw or "").strip()
            if not val or (kind == "email" and "@" not in val):
                continue
        ident = (kind, str(val).lower())
        if ident in seen:
            continue
        seen.add(ident)
        content = c.get("content") if c.get("content") in COPY_CONTENTS and not direction else "tribe"
        out.append({"type": kind, "value": val, "content": content,
                    "squad_ids": _ints(c.get("squad_ids")) if content == "squads" else []})
        if len(out) >= MAX_COPIES:
            break
    return out


def _clean_docs(value, kinds: tuple[str, ...]) -> dict:
    out = {}
    for k in kinds:
        raw = (value or {}).get(k) if isinstance(value, dict) else None
        out[k] = [d for d in DOC_TYPES if d in (raw or [])] if raw is not None else ["weekly"]
    return out


def _clean_body(value, kinds: tuple[str, ...]) -> dict:
    """The blocks of each kind of mail, in the fixed order; unknown ones dropped.
    An empty list is kept: the mail then holds the button and the attachments."""
    out = {}
    for k in kinds:
        raw = (value or {}).get(k) if isinstance(value, dict) else None
        out[k] = [b for b in BODY_SECTIONS if b in raw] if isinstance(raw, list) else list(DEFAULT_BODY[k])
        if k == "squad" and "squads" in out[k]:
            out[k].remove("squads")
    return out


def normalize(base: dict, patch: dict | None) -> dict:
    """``base`` with ``patch`` applied and every field clamped to its range,
    without writing anything (the screen's live plan uses it). The scope
    (``tribe_id``) and the bookkeeping stay those of ``base``."""
    cfg = dict(base)
    for k, v in (patch or {}).items():
        if k in cfg and k not in BOOKKEEPING and k != "tribe_id":
            cfg[k] = v
    direction = cfg.get("tribe_id") is None
    cfg["name"] = str(cfg.get("name") or "").strip()[:MAX_NAME]
    cfg["enabled"] = bool(cfg["enabled"])
    cfg["only_when_changes"] = bool(cfg.get("only_when_changes", False))
    cfg["weekdays"] = _clean_weekdays(cfg.get("weekdays"))
    try:
        cfg["hour"] = max(0, min(23, int(cfg["hour"])))
    except (TypeError, ValueError):
        cfg["hour"] = 8
    try:
        cfg["minute"] = max(0, min(55, int(cfg.get("minute") or 0))) // 5 * 5
    except (TypeError, ValueError):
        cfg["minute"] = 0
    try:
        cfg["since_days"] = max(1, min(120, int(cfg["since_days"])))
    except (TypeError, ValueError):
        cfg["since_days"] = 7
    cfg["last_sent_day"] = str(cfg.get("last_sent_day") or "")
    cfg["copies"] = _clean_copies(cfg.get("copies"), direction)
    if direction:
        cfg["docs"] = _clean_docs(cfg.get("docs"), ("all",))
        cfg["body"] = _clean_body(cfg.get("body"), ("all",))
    else:
        for k in ("leader_tribe", "leader_squads", "copy_leader", "copy_co_leaders", "copy_contributors"):
            cfg[k] = bool(cfg.get(k))
        cfg["squad_ids"] = _ints(cfg.get("squad_ids"))
        cfg["docs"] = _clean_docs(cfg.get("docs"), ("tribe", "squad"))
        cfg["body"] = _clean_body(cfg.get("body"), ("tribe", "squad"))
    return cfg


def save_diffusion(db: Session, cfg: dict) -> dict:
    """Validate and persist a diffusion; a new one (``id`` None) gets its id."""
    base = get_diffusion(db, cfg["id"]) if cfg.get("id") else None
    if base is None:
        base = defaults(cfg.get("tribe_id"))
        base["id"] = cfg.get("id") or _next_id(db)
    out = normalize(base, cfg)
    if "last_sent_day" in cfg:
        out["last_sent_day"] = str(cfg.get("last_sent_day") or "")
    row = db.get(AppSetting, key_of(out["id"]))
    payload = json.dumps({k: v for k, v in out.items() if k != "id"})
    if row is None:
        db.add(AppSetting(key=key_of(out["id"]), value=payload))
    else:
        row.value = payload
    db.flush()
    return out


def create_diffusion(db: Session, tribe_id: int | None, patch: dict | None = None) -> dict:
    return save_diffusion(db, normalize({**defaults(tribe_id), "id": _next_id(db)}, patch))


def delete_diffusion(db: Session, diffusion_id: int) -> bool:
    """Remove a diffusion and its "what's new" baselines."""
    from .models import ReportBaseline
    row = db.get(AppSetting, key_of(diffusion_id))
    if row is None:
        return False
    db.delete(row)
    for b in db.scalars(select(ReportBaseline).where(
            ReportBaseline.scope_key.like(f"d{int(diffusion_id)}:%"))).all():
        db.delete(b)
    db.flush()
    return True


# ---- The earlier shapes, converted once -------------------------------------------

_LEGACY_KEY = "weekly_report"
_LEGACY_TRIBE = "weekly_report:tribe:"
_LEGACY_VERSION = 2
_CALENDAR = ("enabled", "weekdays", "weekday", "hour", "minute", "since_days", "only_when_changes",
             "last_sent_day")


def _legacy_key(tribe_id: int | None) -> str:
    return _LEGACY_KEY if tribe_id is None else f"{_LEGACY_TRIBE}{int(tribe_id)}"


def _load(db: Session, key: str) -> dict | None:
    row = db.get(AppSetting, key)
    return _parse(row.value) if row else None


def _legacy_write(db: Session, tribe_id: int | None, cfg: dict) -> None:
    key = _legacy_key(tribe_id)
    row = db.get(AppSetting, key)
    payload = json.dumps({**cfg, "v": _LEGACY_VERSION})
    if row is None:
        db.add(AppSetting(key=key, value=payload))
    else:
        row.value = payload


def ensure_v2(db: Session) -> bool:
    """Convert settings of the very first shape into the second one, once.

    Direction: the fixed recipients keep the whole document. The "each squad
    leader gets their squad's document" and "each tribe leader gets their tribe"
    switches of the all-tribes schedule become, for every tribe, a tribe schedule
    on the same calendar, the squad leaders (and co-leaders) in copy. A tribe's
    own schedule keeps its calendar; its fixed addresses become copies, and its
    squad leaders switch becomes the role copies. ``ensure_diffusions`` then
    turns each of them into a diffusion.
    """
    from .models import Tribe

    changed = False
    g = _load(db, _LEGACY_KEY)
    legacy_g = g is not None and g.get("v") != _LEGACY_VERSION
    for tid in db.scalars(select(Tribe.id)).all():
        t = _load(db, _legacy_key(tid))
        if t is not None and t.get("v") == _LEGACY_VERSION:
            continue
        if t is not None:
            new = {k: t[k] for k in _CALENDAR if k in t}
            if t.get("attach_pptx") is False:
                new["docs"] = {"tribe": [], "squad": []}
            emails = _clean_recipients(t.get("recipients"))
            content = "tribe" if t.get("global_doc", True) or not t.get("per_squad") else "squads"
            new["copies"] = [{"type": "email", "value": a, "content": content,
                              "squad_ids": t.get("squad_ids") or []} for a in emails]
            if t.get("squad_leaders"):
                new["copy_leader"] = new["copy_co_leaders"] = True
            new["squad_ids"] = t.get("squad_ids") or []
            _legacy_write(db, tid, new)
            changed = True
        elif legacy_g and g.get("enabled") and (g.get("tribe_leader_digest") or g.get("squad_leaders")):
            new = {k: g[k] for k in _CALENDAR if k in g and k != "last_sent_day"}
            if g.get("attach_pptx") is False:
                new["docs"] = {"tribe": [], "squad": []}
            new["copy_leader"] = new["copy_co_leaders"] = True
            _legacy_write(db, tid, new)
            changed = True
    if legacy_g:
        new = {k: g[k] for k in _CALENDAR if k in g}
        if g.get("attach_pptx") is False:
            new["docs"] = {"all": []}
        keep = g.get("global_doc", True) or g.get("per_squad")
        new["recipients"] = (g.get("recipients") or []) if keep else []
        new["enabled"] = bool(g.get("enabled")) and bool(_clean_recipients(new["recipients"]))
        _legacy_write(db, None, new)
        changed = True
    if changed:
        db.flush()
    return changed


def _legacy_to_diffusion(old: dict, tribe_id: int | None) -> dict | None:
    """One schedule of the second shape as a diffusion, or None when it was never
    set up (nothing to show as a card)."""
    patch = {k: old[k] for k in _CALENDAR if k in old and k != "weekday"}
    if "weekdays" not in old and "weekday" in old:
        patch["weekdays"] = [old["weekday"]]
    if "docs" in old:
        patch["docs"] = old["docs"]
    elif old.get("attach_pptx") is False:
        patch["docs"] = {"all": []} if tribe_id is None else {"tribe": [], "squad": []}
    if tribe_id is None:
        patch["copies"] = [{"type": "email", "value": a} for a in _clean_recipients(old.get("recipients"))]
        used = bool(old.get("enabled")) or bool(patch["copies"])
    else:
        per_squad = old.get("leader_mode") == "per_squad"
        patch.update({"leader_tribe": not per_squad, "leader_squads": per_squad,
                      "squad_ids": old.get("squad_ids") or [], "copies": old.get("copies") or []})
        for k in ("copy_leader", "copy_co_leaders", "copy_contributors"):
            patch[k] = bool(old.get(k))
        used = (bool(old.get("enabled")) or bool(patch["copies"]) or per_squad
                or any(patch[k] for k in ("copy_leader", "copy_co_leaders", "copy_contributors")))
    return patch if used else None


def ensure_diffusions(db: Session) -> bool:
    """Turn the schedules of the earlier shapes into diffusions, once. Returns
    True when it did. Each keeps its calendar, its recipients, the day it last
    went out and its "what's new" baselines (renamed under the diffusion), so
    nobody receives a mail twice or loses the week's news."""
    from .models import ReportBaseline, Tribe

    changed = ensure_v2(db)
    rows = db.scalars(select(AppSetting).where(
        (AppSetting.key == _LEGACY_KEY) | AppSetting.key.like(_LEGACY_TRIBE + "%"))).all()
    for row in sorted(rows, key=lambda r: r.key):
        tid = None if row.key == _LEGACY_KEY else row.key[len(_LEGACY_TRIBE):]
        old = _parse(row.value) or {}
        db.delete(row)
        changed = True
        if tid is not None:
            try:
                tid = int(tid)
            except ValueError:
                continue
            if db.get(Tribe, tid) is None:
                continue
        patch = _legacy_to_diffusion(old, tid)
        if patch is None:
            continue
        cfg = create_diffusion(db, tid, patch)
        if old.get("last_sent_day"):
            cfg["last_sent_day"] = str(old["last_sent_day"])
            save_diffusion(db, cfg)
        prefix = "global" if tid is None else f"t{tid}:"
        q = select(ReportBaseline).where(
            ReportBaseline.scope_key == "global" if tid is None else ReportBaseline.scope_key.like(prefix + "%"))
        for b in db.scalars(q).all():
            new_key = f"d{cfg['id']}:{b.scope_key}"
            if db.get(ReportBaseline, new_key) is None:
                db.add(ReportBaseline(scope_key=new_key, signature=b.signature, updated_at=b.updated_at))
    if changed:
        db.flush()
    return changed
