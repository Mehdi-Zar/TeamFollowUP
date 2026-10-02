"""SCIM 2.0 server (RFC 7643 / 7644): the identity provider provisions accounts.

Entra ID, Okta, OneLogin, JumpCloud... call these endpoints to create an account
when someone is assigned the application, update it when the directory changes,
and deactivate it when the person leaves (``active: false``) or is unassigned.

Scope, on purpose:

* **Users** are fully supported: create, read, list with ``filter`` (``userName``,
  ``externalId``, ``emails.value``, ``id`` with ``eq``), replace (PUT), PATCH
  (Entra and Okta forms, with or without ``path``) and DELETE.
* **A DELETE deactivates**, it does not erase: the account's history (reporting,
  audit) stays, an administrator purges it if needed.
* **The persona is never set by SCIM**: an account is created with the persona
  and tribe chosen in Administration > Annuaire, and a provisioning token can
  neither grant nor remove administration. The break-glass account is invisible.
* **Groups are the tribes, read only**: listed so that a connector can read them,
  never written (tribes are managed in the application).

Authentication: ``Authorization: Bearer <token>``, the token generated in
Administration (only its hash is stored). The routes live outside ``/api``: they
are called by a server, not by the application's pages.
"""
from __future__ import annotations

from collections import deque
from datetime import timezone

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import record_audit
from ..directoryconfig import get_directory, scim_token_ok
from ..models import Tribe, User, utcnow

router = APIRouter(prefix="/scim/v2", tags=["scim"], include_in_schema=True)

MEDIA = "application/scim+json"
USER_SCHEMA = "urn:ietf:params:scim:schemas:core:2.0:User"
GROUP_SCHEMA = "urn:ietf:params:scim:schemas:core:2.0:Group"
ENTERPRISE = "urn:ietf:params:scim:schemas:extension:enterprise:2.0:User"
LIST = "urn:ietf:params:scim:api:messages:2.0:ListResponse"
ERROR = "urn:ietf:params:scim:api:messages:2.0:Error"
PATCH_OP = "urn:ietf:params:scim:api:messages:2.0:PatchOp"
MAX_COUNT = 200


class ScimError(Exception):
    def __init__(self, status: int, detail: str, scim_type: str | None = None):
        self.status, self.detail, self.scim_type = status, detail, scim_type


def _json(body: dict, status: int = 200, headers: dict | None = None) -> JSONResponse:
    return JSONResponse(body, status_code=status, media_type=MEDIA, headers=headers)


def _error(exc: ScimError) -> JSONResponse:
    body = {"schemas": [ERROR], "status": str(exc.status), "detail": exc.detail}
    if exc.scim_type:
        body["scimType"] = exc.scim_type
    return _json(body, exc.status)


# The last calls the identity provider made, accepted or refused, for the
# administrator's SCIM test. A refused call leaves no other trace: nothing is
# written, and "the provisioning does nothing" is exactly the case to debug. Kept
# in memory, per process: a debugging aid, not an audit trail (that is audit_log).
RECENT: deque = deque(maxlen=30)


def _remember_call(request: Request, outcome: str) -> None:
    RECENT.appendleft({"at": utcnow().isoformat(), "method": request.method, "path": request.url.path,
                       "query": request.url.query[:200] or None, "outcome": outcome,
                       "client": request.client.host if request.client else None,
                       "agent": (request.headers.get("user-agent") or "")[:80] or None})


def scim_auth(request: Request, db: Session = Depends(get_db)) -> dict:
    """The SCIM settings when the call carries the right token, else a ScimError."""
    cfg = get_directory(db)
    header = request.headers.get("authorization") or ""
    token = header[7:].strip() if header.lower().startswith("bearer ") else None
    if not cfg.get("scim_enabled"):
        _remember_call(request, "refused_disabled")
    elif not token:
        _remember_call(request, "refused_no_token")
    elif not scim_token_ok(cfg, token):
        _remember_call(request, "refused_bad_token")
    else:
        _remember_call(request, "accepted")
        request.state.scim_base = scim_base_url(db, request)
        return cfg
    raise ScimError(401, "Jeton SCIM absent, invalide ou provisioning désactivé")


def install(app) -> None:
    """Answer SCIM errors in the SCIM format (application/scim+json)."""
    @app.exception_handler(ScimError)
    async def _scim_error(request, exc: ScimError):  # noqa: ANN001
        return _error(exc)


def scim_base_url(db: Session, request: Request) -> str:
    """The SCIM endpoint under the application's public URL, the one OIDC and SAML
    callbacks are built on (Administration > Authentification), and not the
    address the container happens to be reached at."""
    from ..authconfig import get_auth_config
    base = (get_auth_config(db, request).get("base_url_effective") or str(request.base_url)).rstrip("/")
    return f"{base}/scim/v2"


def _base(request: Request) -> str:
    # Set by scim_auth, which every route goes through and which has the session.
    return getattr(request.state, "scim_base", None) or str(request.base_url).rstrip("/") + "/scim/v2"


def _iso(dt) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat().replace("+00:00", "Z")


def _split_name(display: str) -> tuple[str | None, str | None]:
    parts = (display or "").split(" ", 1)
    return (parts[0] or None, parts[1] if len(parts) > 1 else None)


def _user_out(u: User, request: Request) -> dict:
    given, family = _split_name(u.display_name)
    out = {
        "schemas": [USER_SCHEMA],
        "id": str(u.id),
        "userName": u.email,
        "displayName": u.display_name,
        "name": {"formatted": u.display_name, "givenName": given, "familyName": family},
        "emails": [{"value": u.email, "type": "work", "primary": True}],
        "active": u.status == "active",
        "meta": {"resourceType": "User", "location": f"{_base(request)}/Users/{u.id}",
                 "created": _iso(getattr(u, "created_at", None))},
    }
    if u.scim_external_id:
        out["externalId"] = u.scim_external_id
    return out


def _visible_users(db: Session):
    return select(User).where(User.is_break_glass.is_(False))


def _get_user(db: Session, user_id: str) -> User:
    try:
        u = db.get(User, int(user_id))
    except (TypeError, ValueError):
        u = None
    if u is None or u.is_break_glass:
        raise ScimError(404, f"Utilisateur {user_id} introuvable")
    return u


def _email_of(body: dict) -> str | None:
    """The account email: the primary (or first) email, else a userName that is one."""
    emails = body.get("emails") or []
    if isinstance(emails, list) and emails:
        prim = next((e for e in emails if isinstance(e, dict) and e.get("primary")), None) or emails[0]
        if isinstance(prim, dict) and "@" in str(prim.get("value") or ""):
            return str(prim["value"]).strip().lower()
    un = str(body.get("userName") or "").strip().lower()
    return un if "@" in un else None


def _display_of(body: dict, fallback: str) -> str:
    name = body.get("name") or {}
    joined = " ".join(x for x in (name.get("givenName"), name.get("familyName")) if x)
    return (body.get("displayName") or name.get("formatted") or joined or fallback).strip()[:255]


def _as_bool(v) -> bool:
    if isinstance(v, str):
        return v.strip().lower() == "true"
    return bool(v)


def _email_taken(db: Session, email: str, except_id: int | None = None) -> bool:
    q = select(User.id).where(func.lower(User.email) == email)
    if except_id is not None:
        q = q.where(User.id != except_id)
    return db.scalars(q).first() is not None


def _set_active(db: Session, u: User, active: bool) -> None:
    before = u.status
    if active and u.status != "active":
        u.status = "active"
    elif not active and u.status != "disabled":
        u.status = "disabled"
        from .admin import _bump_session
        _bump_session(u)  # his open sessions end now
    if u.status != before:
        record_audit(db, None, "scim.user_status", entity="user", entity_id=u.id,
                     detail={"from": before, "to": u.status})


async def _body(request: Request) -> dict:
    try:
        data = await request.json()
    except Exception:
        raise ScimError(400, "Corps JSON invalide", "invalidSyntax")
    if not isinstance(data, dict):
        raise ScimError(400, "Corps JSON invalide", "invalidSyntax")
    return data


# ---------- discovery ----------
@router.get("/ServiceProviderConfig")
def service_provider_config(request: Request, cfg: dict = Depends(scim_auth)):
    """GET /scim/v2/ServiceProviderConfig: what this server supports."""
    return _json({
        "schemas": ["urn:ietf:params:scim:schemas:core:2.0:ServiceProviderConfig"],
        "patch": {"supported": True},
        "bulk": {"supported": False, "maxOperations": 0, "maxPayloadSize": 0},
        "filter": {"supported": True, "maxResults": MAX_COUNT},
        "changePassword": {"supported": False},
        "sort": {"supported": False},
        "etag": {"supported": False},
        "authenticationSchemes": [{"type": "oauthbearertoken", "name": "OAuth Bearer Token",
                                   "description": "Jeton généré dans Administration > Annuaire", "primary": True}],
        "meta": {"resourceType": "ServiceProviderConfig", "location": f"{_base(request)}/ServiceProviderConfig"},
    })


@router.get("/ResourceTypes")
def resource_types(request: Request, cfg: dict = Depends(scim_auth)):
    """GET /scim/v2/ResourceTypes: User and Group."""
    res = [
        {"schemas": ["urn:ietf:params:scim:schemas:core:2.0:ResourceType"], "id": "User", "name": "User",
         "endpoint": "/Users", "schema": USER_SCHEMA,
         "schemaExtensions": [{"schema": ENTERPRISE, "required": False}],
         "meta": {"resourceType": "ResourceType", "location": f"{_base(request)}/ResourceTypes/User"}},
        {"schemas": ["urn:ietf:params:scim:schemas:core:2.0:ResourceType"], "id": "Group", "name": "Group",
         "endpoint": "/Groups", "schema": GROUP_SCHEMA,
         "meta": {"resourceType": "ResourceType", "location": f"{_base(request)}/ResourceTypes/Group"}},
    ]
    return _json({"schemas": [LIST], "totalResults": len(res), "startIndex": 1, "itemsPerPage": len(res),
                  "Resources": res})


def _attr(name, type_="string", **kw) -> dict:
    a = {"name": name, "type": type_, "multiValued": False, "required": False, "caseExact": False,
         "mutability": "readWrite", "returned": "default", "uniqueness": "none"}
    a.update(kw)
    return a


@router.get("/Schemas")
def schemas(request: Request, cfg: dict = Depends(scim_auth)):
    """GET /scim/v2/Schemas: the User attributes this server reads and returns."""
    user = {
        "id": USER_SCHEMA, "name": "User", "description": "Compte de l'application",
        "attributes": [
            _attr("userName", required=True, uniqueness="server"),
            _attr("displayName"),
            _attr("externalId", caseExact=True),
            _attr("active", "boolean"),
            _attr("name", "complex", subAttributes=[_attr("formatted"), _attr("givenName"), _attr("familyName")]),
            _attr("emails", "complex", multiValued=True,
                  subAttributes=[_attr("value"), _attr("type"), _attr("primary", "boolean")]),
        ],
        "meta": {"resourceType": "Schema", "location": f"{_base(request)}/Schemas/{USER_SCHEMA}"},
    }
    group = {
        "id": GROUP_SCHEMA, "name": "Group", "description": "Tribe (lecture seule)",
        "attributes": [_attr("displayName", mutability="readOnly"),
                       _attr("members", "complex", multiValued=True, mutability="readOnly",
                             subAttributes=[_attr("value", mutability="readOnly")])],
        "meta": {"resourceType": "Schema", "location": f"{_base(request)}/Schemas/{GROUP_SCHEMA}"},
    }
    return _json({"schemas": [LIST], "totalResults": 2, "startIndex": 1, "itemsPerPage": 2,
                  "Resources": [user, group]})


# ---------- Users ----------
def _parse_filter(flt: str | None) -> tuple[str, str] | None:
    """``attr eq "value"`` (the only operator connectors use to find an account)."""
    if not flt:
        return None
    import re
    m = re.match(r'^\s*([\w.\[\]" ]+?)\s+eq\s+"((?:[^"\\]|\\.)*)"\s*$', flt, re.IGNORECASE)
    if not m:
        raise ScimError(400, "Filtre non pris en charge (attendu : attribut eq \"valeur\")", "invalidFilter")
    attr = m.group(1).replace(" ", "").lower()
    return attr, m.group(2).replace('\\"', '"')


@router.get("/Users")
def list_users(request: Request, filter: str | None = None, startIndex: int = 1, count: int = 100,
               db: Session = Depends(get_db), cfg: dict = Depends(scim_auth)):
    """GET /scim/v2/Users?filter=userName eq "x"&startIndex=&count=."""
    q = _visible_users(db)
    f = _parse_filter(filter)
    if f:
        attr, val = f
        if attr == "username" or (attr.startswith("emails") and attr.endswith("value")):
            q = q.where(func.lower(User.email) == val.strip().lower())
        elif attr == "externalid":
            q = q.where(User.scim_external_id == val)
        elif attr == "id":
            q = q.where(User.id == (int(val) if val.isdigit() else -1))
        else:
            raise ScimError(400, f"Filtre non pris en charge sur {attr}", "invalidFilter")
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    start = max(1, int(startIndex or 1))
    count = max(0, min(int(count if count is not None else 100), MAX_COUNT))
    rows = db.scalars(q.order_by(User.id).offset(start - 1).limit(count)).all() if count else []
    return _json({"schemas": [LIST], "totalResults": total, "startIndex": start, "itemsPerPage": len(rows),
                  "Resources": [_user_out(u, request) for u in rows]})


@router.get("/Users/{user_id}")
def get_user(user_id: str, request: Request, db: Session = Depends(get_db), cfg: dict = Depends(scim_auth)):
    """GET /scim/v2/Users/{id}."""
    return _json(_user_out(_get_user(db, user_id), request))


@router.post("/Users")
async def create_user(request: Request, db: Session = Depends(get_db), cfg: dict = Depends(scim_auth)):
    """POST /scim/v2/Users: create the account (persona and tribe from the settings).

    409 ``uniqueness`` when an account already has that email: the connector then
    looks it up (filter) and links it."""
    body = await _body(request)
    email = _email_of(body)
    if not email:
        raise ScimError(400, "userName ou emails doit contenir une adresse email", "invalidValue")
    if _email_taken(db, email):
        raise ScimError(409, f"Un compte existe déjà pour {email}", "uniqueness")
    tribe_id = cfg.get("scim_default_tribe_id")
    if tribe_id is not None and db.get(Tribe, tribe_id) is None:
        tribe_id = None
    role = cfg.get("scim_default_role") or "member"
    if role == "admin":
        role = "member"
    u = User(email=email, display_name=_display_of(body, email.split("@")[0]), role=role,
             tribe_id=tribe_id, status="active" if _as_bool(body.get("active", True)) else "disabled",
             scim_external_id=(str(body["externalId"])[:255] if body.get("externalId") else None))
    db.add(u)
    db.flush()
    from ..memberlink import link_members_to
    link_members_to(db, u)
    record_audit(db, None, "scim.user_create", entity="user", entity_id=u.id,
                 detail={"email": email, "role": role, "tribe_id": tribe_id})
    db.commit()
    db.refresh(u)
    return _json(_user_out(u, request), 201, {"Location": f"{_base(request)}/Users/{u.id}"})


def _apply_email(db: Session, u: User, email: str | None) -> None:
    if email and email != u.email.lower():
        if _email_taken(db, email, u.id):
            raise ScimError(409, f"Un compte existe déjà pour {email}", "uniqueness")
        u.email = email
        from ..memberlink import link_members_to
        link_members_to(db, u)


@router.put("/Users/{user_id}")
async def replace_user(user_id: str, request: Request, db: Session = Depends(get_db),
                       cfg: dict = Depends(scim_auth)):
    """PUT /scim/v2/Users/{id}: replace name, email, externalId and active."""
    u = _get_user(db, user_id)
    body = await _body(request)
    _apply_email(db, u, _email_of(body))
    u.display_name = _display_of(body, u.display_name)
    if "externalId" in body:
        u.scim_external_id = str(body["externalId"])[:255] if body["externalId"] else None
    if "active" in body:
        _set_active(db, u, _as_bool(body["active"]))
    record_audit(db, None, "scim.user_update", entity="user", entity_id=u.id)
    db.commit()
    db.refresh(u)
    return _json(_user_out(u, request))


def _patch_value(u: User, db: Session, path: str | None, value, op: str) -> None:
    """One PATCH operation. ``path`` None means ``value`` is a dict of attributes
    (Entra and Okta both send ``{"active": false}`` that way)."""
    if not path:
        if not isinstance(value, dict):
            raise ScimError(400, "Opération PATCH sans path : la valeur doit être un objet", "invalidValue")
        for k, v in value.items():
            _patch_value(u, db, k, v, op)
        return
    p = path.strip()
    pl = p.lower()
    if op == "remove":
        if pl == "externalid":
            u.scim_external_id = None
        return  # the other attributes are required or derived: nothing to remove
    if pl == "active":
        _set_active(db, u, _as_bool(value))
    elif pl == "username":
        v = str(value or "").strip().lower()
        if "@" in v:
            _apply_email(db, u, v)
    elif pl.startswith("emails"):
        v = value
        if isinstance(v, list) and v:
            v = (next((e for e in v if isinstance(e, dict) and e.get("primary")), None) or v[0]).get("value")
        elif isinstance(v, dict):
            v = v.get("value")
        v = str(v or "").strip().lower()
        if "@" in v:
            _apply_email(db, u, v)
    elif pl == "displayname":
        if value:
            u.display_name = str(value).strip()[:255]
    elif pl in ("name.givenname", "name.familyname", "name.formatted", "name"):
        given, family = _split_name(u.display_name)
        if pl == "name" and isinstance(value, dict):
            given = value.get("givenName", given)
            family = value.get("familyName", family)
            formatted = value.get("formatted")
        else:
            formatted = value if pl == "name.formatted" else None
            if pl == "name.givenname":
                given = value
            elif pl == "name.familyname":
                family = value
        name = formatted or " ".join(x for x in (given, family) if x)
        if name:
            u.display_name = str(name).strip()[:255]
    elif pl == "externalid":
        u.scim_external_id = str(value)[:255] if value else None
    # Any other attribute (title, phone, enterprise extension...) is accepted and
    # ignored: the application does not keep it, and refusing it would stop the
    # connector's whole synchronisation.


@router.patch("/Users/{user_id}")
async def patch_user(user_id: str, request: Request, db: Session = Depends(get_db),
                     cfg: dict = Depends(scim_auth)):
    """PATCH /scim/v2/Users/{id}: ``Operations`` add / replace / remove."""
    u = _get_user(db, user_id)
    body = await _body(request)
    ops = body.get("Operations") or body.get("operations")
    if not isinstance(ops, list):
        raise ScimError(400, "Operations manquant", "invalidSyntax")
    for o in ops:
        if not isinstance(o, dict):
            raise ScimError(400, "Opération invalide", "invalidSyntax")
        op = str(o.get("op") or "").lower()
        if op not in ("add", "replace", "remove"):
            raise ScimError(400, f"Opération inconnue : {o.get('op')}", "invalidSyntax")
        _patch_value(u, db, o.get("path"), o.get("value"), op)
    record_audit(db, None, "scim.user_update", entity="user", entity_id=u.id)
    db.commit()
    db.refresh(u)
    return _json(_user_out(u, request))


@router.delete("/Users/{user_id}")
def delete_user(user_id: str, db: Session = Depends(get_db), cfg: dict = Depends(scim_auth)):
    """DELETE /scim/v2/Users/{id}: deactivates the account (204); its history stays."""
    u = _get_user(db, user_id)
    _set_active(db, u, False)
    record_audit(db, None, "scim.user_delete", entity="user", entity_id=u.id)
    db.commit()
    return Response(status_code=204)


# ---------- Groups (tribes, read only) ----------
def _group_out(t: Tribe, db: Session, request: Request) -> dict:
    members = db.scalars(_visible_users(db).where(User.tribe_id == t.id).order_by(User.id)).all()
    return {"schemas": [GROUP_SCHEMA], "id": str(t.id), "displayName": t.name,
            "members": [{"value": str(m.id), "display": m.display_name} for m in members],
            "meta": {"resourceType": "Group", "location": f"{_base(request)}/Groups/{t.id}"}}


@router.get("/Groups")
def list_groups(request: Request, filter: str | None = None, startIndex: int = 1, count: int = 100,
                db: Session = Depends(get_db), cfg: dict = Depends(scim_auth)):
    """GET /scim/v2/Groups: the tribes, read only."""
    q = select(Tribe)
    f = _parse_filter(filter)
    if f:
        attr, val = f
        if attr == "displayname":
            q = q.where(Tribe.name == val)
        elif attr == "id":
            q = q.where(Tribe.id == (int(val) if val.isdigit() else -1))
        else:
            raise ScimError(400, f"Filtre non pris en charge sur {attr}", "invalidFilter")
    rows = db.scalars(q.order_by(Tribe.id)).all()
    start = max(1, int(startIndex or 1))
    count = max(0, min(int(count if count is not None else 100), MAX_COUNT))
    page = rows[start - 1:start - 1 + count]
    return _json({"schemas": [LIST], "totalResults": len(rows), "startIndex": start, "itemsPerPage": len(page),
                  "Resources": [_group_out(t, db, request) for t in page]})


@router.get("/Groups/{group_id}")
def get_group(group_id: str, request: Request, db: Session = Depends(get_db), cfg: dict = Depends(scim_auth)):
    """GET /scim/v2/Groups/{id}."""
    t = db.get(Tribe, int(group_id)) if group_id.isdigit() else None
    if t is None:
        raise ScimError(404, f"Groupe {group_id} introuvable")
    return _json(_group_out(t, db, request))


def _read_only_groups():
    raise ScimError(403, "Les groupes (tribes) sont en lecture seule : ils se gèrent dans l'application",
                    "mutability")


@router.post("/Groups")
def create_group(cfg: dict = Depends(scim_auth)):
    """Groups are the tribes and are managed in the application: refused (403)."""
    _read_only_groups()


@router.put("/Groups/{group_id}")
def replace_group(group_id: str, cfg: dict = Depends(scim_auth)):
    """Groups are read only: refused (403)."""
    _read_only_groups()


@router.patch("/Groups/{group_id}")
def patch_group(group_id: str, cfg: dict = Depends(scim_auth)):
    """Groups are read only: refused (403)."""
    _read_only_groups()


@router.delete("/Groups/{group_id}")
def delete_group(group_id: str, cfg: dict = Depends(scim_auth)):
    """Groups are read only: refused (403)."""
    _read_only_groups()
