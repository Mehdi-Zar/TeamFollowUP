"""Scheduled report settings, stored in DB (like SMTP/general).

Two kinds of schedule, same calendar fields, sent by report.send_due_weekly_reports:

  * the "Direction" schedule (app_settings['weekly_report'], admin only): the
    whole document, every tribe, to fixed addresses;
  * one schedule per tribe (app_settings['weekly_report:tribe:<id>'], set by the
    tribe leader for their tribe, or by the admin): the tribe leader is the main
    recipient and gets either the tribe's document or one mail per squad
    (``leader_mode``); others are added in copy:
      - by their role in each squad (leader, co-leaders, contributors): always
        in copy of THEIR squad's mail, never of another squad's;
      - by persona, by name, or by address (``copies``), each with what it gets:
        the tribe's document, or the mails of the chosen squads.

Who receives what is computed in app/mailplan.py. Settings written before this
shape (version 1: global_doc, per_squad, squad_leaders, tribe_leader_digest) are
converted once by ``ensure_v2``.
"""
import json

from sqlalchemy.orm import Session

from .models import AppSetting

REPORT_KEY = "weekly_report"
TRIBE_PREFIX = "weekly_report:tribe:"
VERSION = 2
LEADER_MODES = ("tribe", "per_squad")
COPY_TYPES = ("persona", "user", "email")
COPY_CONTENTS = ("tribe", "squads")
MAX_COPIES = 50
# The documents a mail can carry, as PowerPoint attachments: the weekly report
# (whose summary is also the mail's body), the dashboard, the roadmap and the
# dependencies. Chosen per kind of mail: the Direction's ("all"), a tribe's
# document ("tribe") and the squad mails ("squad").
DOC_TYPES = ("weekly", "dashboard", "roadmap", "dependencies")


def key_for(tribe_id: int | None) -> str:
    """The app_settings key of the Direction schedule (None) or of a tribe's."""
    return REPORT_KEY if tribe_id is None else f"{TRIBE_PREFIX}{int(tribe_id)}"


def tribe_schedules(db: Session) -> list[int]:
    """The tribes that have a schedule of their own."""
    from sqlalchemy import select
    keys = db.scalars(select(AppSetting.key).where(AppSetting.key.like(TRIBE_PREFIX + "%"))).all()
    out = []
    for k in keys:
        try:
            out.append(int(k[len(TRIBE_PREFIX):]))
        except ValueError:
            continue
    return sorted(out)


def _common() -> dict:
    """The calendar and the options every schedule has."""
    return {
        "v": VERSION,
        "enabled": False,
        # Days of the week to send on (0 = Monday ... 6 = Sunday), Paris time.
        "weekdays": [0],
        "hour": 8,
        # Look-back window of the "what's new" section.
        "since_days": 7,
        # Each mail goes out only when ITS document changed since it was last sent.
        "only_when_changes": False,
        # Bookkeeping: ISO date already sent today (per-day idempotency).
        "last_sent_day": "",
    }


def _defaults(tribe_id: int | None) -> dict:
    cfg = _common()
    if tribe_id is None:
        cfg["recipients"] = []
        cfg["docs"] = {"all": ["weekly"]}
    else:
        cfg.update({
            # What the tribe leader receives: "tribe" (one document) or "per_squad".
            "leader_mode": "tribe",
            # The squads the squad mails cover (empty = every squad of the tribe).
            "squad_ids": [],
            # In copy of their own squad's mail.
            "copy_leader": False,
            "copy_co_leaders": False,
            "copy_contributors": False,
            # Other copies: {"type": persona|user|email, "value", "content": tribe|squads, "squad_ids"}.
            "copies": [],
            "docs": {"tribe": ["weekly"], "squad": ["weekly"]},
        })
    return cfg


def get_report(db: Session, tribe_id: int | None = None) -> dict:
    """The effective settings of a schedule (defaults for what is not stored)."""
    cfg = _defaults(tribe_id)
    row = db.get(AppSetting, key_for(tribe_id))
    if row:
        try:
            stored = json.loads(row.value)
            cfg.update({k: v for k, v in stored.items() if k in cfg})
            # Before the choice of documents, "attach the PPTX" off meant none.
            if "docs" not in stored and stored.get("attach_pptx") is False:
                cfg["docs"] = {k: [] for k in cfg["docs"]}
            if "weekdays" not in stored and "weekday" in stored:
                cfg["weekdays"] = [stored["weekday"]]
        except (json.JSONDecodeError, TypeError, AttributeError):
            pass
    cfg["v"] = VERSION
    if not cfg.get("weekdays"):
        cfg["weekdays"] = [0]
    return cfg


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


def _clean_copies(value) -> list[dict]:
    """Keep the well-formed copies, once each (same type and value)."""
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
        content = c.get("content") if c.get("content") in COPY_CONTENTS else "tribe"
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


def normalize(db: Session, patch: dict, tribe_id: int | None = None) -> dict:
    """The saved settings with ``patch`` applied and every field clamped to its
    range, without writing anything (the screen's live plan uses it)."""
    cfg = get_report(db, tribe_id)
    for k, v in (patch or {}).items():
        if k in cfg and k != "v":
            cfg[k] = v
    cfg["enabled"] = bool(cfg["enabled"])
    cfg["only_when_changes"] = bool(cfg.get("only_when_changes", False))
    cfg["weekdays"] = _clean_weekdays(cfg.get("weekdays"))
    try:
        cfg["hour"] = max(0, min(23, int(cfg["hour"])))
    except (TypeError, ValueError):
        cfg["hour"] = 8
    try:
        cfg["since_days"] = max(1, min(120, int(cfg["since_days"])))
    except (TypeError, ValueError):
        cfg["since_days"] = 7
    cfg["last_sent_day"] = str(cfg.get("last_sent_day") or "")
    if tribe_id is None:
        cfg["recipients"] = _clean_recipients(cfg.get("recipients"))
        cfg["docs"] = _clean_docs(cfg.get("docs"), ("all",))
    else:
        cfg["leader_mode"] = cfg.get("leader_mode") if cfg.get("leader_mode") in LEADER_MODES else "tribe"
        cfg["squad_ids"] = _ints(cfg.get("squad_ids"))
        for k in ("copy_leader", "copy_co_leaders", "copy_contributors"):
            cfg[k] = bool(cfg.get(k))
        cfg["copies"] = _clean_copies(cfg.get("copies"))
        cfg["docs"] = _clean_docs(cfg.get("docs"), ("tribe", "squad"))
    return cfg


def set_report(db: Session, patch: dict, tribe_id: int | None = None) -> dict:
    """Validate and persist a schedule update (see ``normalize``)."""
    cfg = normalize(db, patch, tribe_id)
    _write(db, key_for(tribe_id), cfg)
    return cfg


def _write(db: Session, key: str, cfg: dict) -> None:
    row = db.get(AppSetting, key)
    payload = json.dumps(cfg)
    if row is None:
        db.add(AppSetting(key=key, value=payload))
    else:
        row.value = payload


def _load(db: Session, key: str) -> dict | None:
    row = db.get(AppSetting, key)
    if row is None:
        return None
    try:
        out = json.loads(row.value)
        return out if isinstance(out, dict) else None
    except (json.JSONDecodeError, TypeError):
        return None


_CALENDAR = ("enabled", "weekdays", "weekday", "hour", "since_days", "only_when_changes",
             "last_sent_day")


def ensure_v2(db: Session) -> bool:
    """Convert settings of the first shape, once. Returns True when it did.

    Direction: the fixed recipients keep the whole document (they also had it
    when they got one mail per squad: that split is now the squads' own mails).
    The "each squad leader gets their squad's document" and "each tribe leader
    gets their tribe" switches of the all-tribes schedule become, for every
    tribe, a tribe schedule on the same calendar, its leader receiving the
    tribe's document and the squad leaders (and co-leaders) in copy of their
    squad's mail. A tribe's own schedule keeps its calendar; its fixed addresses
    become copies (of the tribe's document, or of the squads' mails), and its
    squad leaders switch becomes the role copies.
    """
    from sqlalchemy import select
    from .models import Tribe

    changed = False
    g = _load(db, REPORT_KEY)
    tribe_ids = db.scalars(select(Tribe.id)).all()
    legacy_g = g is not None and g.get("v") != VERSION
    for tid in tribe_ids:
        t = _load(db, key_for(tid))
        if t is not None and t.get("v") == VERSION:
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
            set_report(db, new, tid)
            changed = True
        elif legacy_g and g.get("enabled") and (g.get("tribe_leader_digest") or g.get("squad_leaders")):
            new = {k: g[k] for k in _CALENDAR if k in g and k != "last_sent_day"}
            if g.get("attach_pptx") is False:
                new["docs"] = {"tribe": [], "squad": []}
            new["copy_leader"] = new["copy_co_leaders"] = True
            set_report(db, new, tid)
            changed = True
    if legacy_g:
        new = {k: g[k] for k in _CALENDAR if k in g}
        if g.get("attach_pptx") is False:
            new["docs"] = {"all": []}
        keep = g.get("global_doc", True) or g.get("per_squad")
        new["recipients"] = (g.get("recipients") or []) if keep else []
        new["enabled"] = bool(g.get("enabled")) and bool(_clean_recipients(new["recipients"]))
        set_report(db, new, None)
        changed = True
    if changed:
        db.flush()
    return changed
