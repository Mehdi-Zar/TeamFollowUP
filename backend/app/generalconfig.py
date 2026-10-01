"""General app configuration stored in DB (branding, default language/year, feed),
editable from the admin Settings. Stored as one JSON blob in app_settings['general'].
"""
import json
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from .config import settings
from .models import AppSetting

GENERAL_KEY = "general"


ORG_VIEWS = ("tree", "list")


def _org_views(value) -> list[str]:
    """The org chart views in the chosen order: known ones, each once, and any
    missing one after (a view is reordered, never lost)."""
    picked = [v for v in (value if isinstance(value, list) else []) if v in ORG_VIEWS]
    picked = list(dict.fromkeys(picked))
    return picked + [v for v in ORG_VIEWS if v not in picked]


# The roles offered for a squad member, in this order; "other" (free text) is
# always offered on top. Editable in Administration.
MEMBER_ROLES = ["Tech lead", "Architecte", "DevOps", "Développeur", "SRE",
                "Product owner", "Scrum master", "QA"]


def _member_roles(value) -> list[str]:
    """A clean role list: trimmed, each once (case-insensitive), at most 50 of 80
    characters. An empty or malformed list falls back to the defaults."""
    out, seen = [], set()
    for v in value if isinstance(value, list) else []:
        name = str(v or "").strip()[:80]
        if name and name.lower() not in seen:
            seen.add(name.lower())
            out.append(name)
    return out[:50] or list(MEMBER_ROLES)


def _defaults() -> dict:
    """The baseline general settings, used when nothing is stored yet.

    Seed values come from environment-driven `settings` where relevant so a fresh
    DB reflects the deployment's configured defaults.
    """
    return {
        "app_name": settings.app_name,
        "app_subtitle": "Pilotage de la tribe",
        "default_lang": "fr",
        # Whether everyone may pick their own language (the FR/EN selector). Off,
        # the whole instance reads in default_lang.
        "lang_switch": True,
        "default_year": datetime.now(timezone.utc).year,
        "staleness_threshold_days": settings.staleness_threshold_days,
        "feed_post_scope": "leaders",   # leaders | everyone
        "feed_retention_days": 0,        # 0 = keep all
        # The org chart's views in their order: the first opens by default.
        "org_views": list(ORG_VIEWS),
        # The roles a squad member is given from (plus "other", free text).
        "member_roles": list(MEMBER_ROLES),
    }


KEYS = set(_defaults().keys())


def get_general(db: Session) -> dict:
    """Cached per request (see configcache); the stored value is read once."""
    from .configcache import cached
    return cached(db, "get_general", _get_general_uncached)


def _get_general_uncached(db: Session) -> dict:
    """Return the effective general config: defaults overlaid with stored values.

    Reads the single JSON blob at app_settings['general']. Unknown keys in the
    stored blob are ignored (filtered by KEYS) so stale/renamed fields cannot leak
    in; a corrupt blob silently falls back to defaults rather than erroring.
    """
    cfg = _defaults()
    row = db.get(AppSetting, GENERAL_KEY)
    if row:
        try:
            stored = json.loads(row.value)
            cfg.update({k: v for k, v in stored.items() if k in KEYS})
        except (json.JSONDecodeError, TypeError):
            pass
    return cfg


def reference_year(db: Session) -> int:
    """The year every screen opens on when none is asked: the instance's default
    year (General settings), not the server clock. Otherwise a tribe preparing
    next year, or working in early January, sees one year in the browser and
    another in every call that leaves the year out."""
    try:
        return int(get_general(db)["default_year"])
    except (TypeError, ValueError):
        return datetime.now(timezone.utc).year


def set_general(db: Session, patch: dict) -> dict:
    """Apply a partial update to the general config and persist it.

    Only whitelisted keys (KEYS) from `patch` are accepted, then every value is
    sanitized/clamped so a malformed admin request can never store an out-of-range
    or invalid setting. Upserts the JSON blob and returns the new effective config.
    """
    cfg = get_general(db)
    for k, v in patch.items():
        if k in KEYS:
            cfg[k] = v
    # sanitize: clamp/normalize every field so bad input falls back to a safe value
    try:
        cfg["staleness_threshold_days"] = max(1, min(365, int(cfg["staleness_threshold_days"])))
    except (TypeError, ValueError):
        cfg["staleness_threshold_days"] = settings.staleness_threshold_days
    if cfg.get("default_lang") not in ("fr", "en"):
        cfg["default_lang"] = "fr"
    cfg["lang_switch"] = bool(cfg.get("lang_switch", True))
    if cfg.get("feed_post_scope") not in ("leaders", "everyone"):
        cfg["feed_post_scope"] = "leaders"
    try:
        cfg["feed_retention_days"] = max(0, int(cfg["feed_retention_days"]))
    except (TypeError, ValueError):
        cfg["feed_retention_days"] = 0
    cfg["org_views"] = _org_views(cfg.get("org_views"))
    cfg["member_roles"] = _member_roles(cfg.get("member_roles"))

    row = db.get(AppSetting, GENERAL_KEY)
    payload = json.dumps(cfg)
    if row is None:
        db.add(AppSetting(key=GENERAL_KEY, value=payload))
    else:
        row.value = payload
    return cfg


def public_config(db: Session) -> dict:
    """The unauthenticated config surface consumed by the SPA at /api/config.

    Exposes only branding/language/feed defaults plus the module switches - never
    secrets. SMTP is reduced to a single `smtp_enabled` boolean (host/credentials
    stay server-side). Imports are local to avoid a circular import at module load.
    """
    from .smtpconfig import get_smtp
    from .modulesconfig import get_modules
    from .branding import css_variables, get_branding
    cfg = get_general(db)
    theme = get_branding(db)
    from .ops import APP_VERSION
    return {
        # The release, shown on the login page and in the sidebar.
        "version": APP_VERSION,
        "app_name": cfg["app_name"],
        "app_subtitle": cfg["app_subtitle"],
        "default_lang": cfg["default_lang"],
        "lang_switch": bool(cfg.get("lang_switch", True)),
        "default_year": cfg["default_year"],
        "feed_post_scope": cfg["feed_post_scope"],
        "org_views": _org_views(cfg.get("org_views")),
        "member_roles": _member_roles(cfg.get("member_roles")),
        "smtp_enabled": bool(get_smtp(db).get("enabled")),
        "modules": get_modules(db),
        # L'apparence voyage avec la configuration publique: la page de connexion
        # en a besoin avant toute authentification, et la faire charger par un
        # second appel ferait clignoter le theme par defaut a chaque ouverture.
        "branding": {
            "css": css_variables(theme),
            "logo": theme["logo"],
            "favicon": theme["favicon"],
            "login_background": theme["login_background"],
            "density": theme["density"],
        },
    }
