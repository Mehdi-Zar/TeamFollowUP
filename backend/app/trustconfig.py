"""The trusted-authority store, DB-backed (AppSetting key ``trust``).

One concern only: what this application accepts when it *calls* something. A
deployment sits behind a load balancer that terminates TLS (ADR 0013), and it
still calls an internal IdP, an internal SMTP relay and a log sink, endpoints
routinely issued by a private authority no public trust store knows about.
Importing that authority here is the supported way to reach them; disabling
verification is not, and no code path offers it.

The DB blob is the source of truth. Every mutation persists it and re-applies
the merged bundle through :mod:`trust`, so a newly imported authority is
effective on the next outbound call, with no restart.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from . import certinfo, trust
from .models import AppSetting

log = logging.getLogger("trt.tls")

TRUST_KEY = "trust"


def _defaults() -> dict:
    """The empty store shape: the admin-managed authorities, root and intermediate."""
    return {"cas": []}


def _read(db: Session) -> dict:
    """Load the store from the DB, falling back to an empty one."""
    cfg = _defaults()
    row = db.get(AppSetting, TRUST_KEY)
    if row:
        try:
            cfg.update({k: v for k, v in json.loads(row.value).items() if k in cfg})
        except (json.JSONDecodeError, TypeError):
            pass
    return cfg


def _write(db: Session, cfg: dict) -> None:
    """Upsert the store. Does not commit: the caller commits then applies."""
    row = db.get(AppSetting, TRUST_KEY)
    payload = json.dumps(cfg)
    if row is None:
        db.add(AppSetting(key=TRUST_KEY, value=payload))
    else:
        row.value = payload


def _now_iso() -> str:
    """Current UTC timestamp as ISO-8601 (recorded as a CA's `added_at`)."""
    return datetime.now(timezone.utc).isoformat()


def _ca_entry(pem: str, name: str | None) -> dict:
    """Build a CA-store record from a certificate PEM (raises on bad PEM)."""
    info = certinfo.cert_info(pem)
    return {
        "id": info["fingerprint_sha256"].replace(":", "")[:32].lower(),
        "name": name or info["subject"],
        "kind": certinfo.ca_kind(pem),
        "pem": certinfo.normalize_cert_pem(pem),
        "subject": info["subject"],
        "issuer": info["issuer"],
        "not_after": info["not_after"],
        "fingerprint": info["fingerprint_sha256"],
        "added_at": _now_iso(),
    }


def _trust_pems(cfg: dict) -> list[str]:
    """Every certificate in the store, whatever its kind.

    Roots and intermediates are both required to verify a privately issued
    endpoint: the root anchors the chain, the intermediates close it when the
    server does not send them itself.
    """
    return [c["pem"] for c in cfg.get("cas", []) if c.get("pem")]


def ensure_trust(db: Session) -> int:
    """Boot hook: make the store effective for outbound TLS.

    Returns the number of authorities applied, for the startup log.
    """
    pems = _trust_pems(_read(db))
    trust.apply(pems)
    return len(pems)


def add_ca(db: Session, pem: str, name: str | None = None) -> dict:
    """Add one or more CA certificates (root and/or intermediate) to the store.

    The authority is trusted on the spot, with no restart, which is what makes a
    privately issued IdP or SMTP relay reachable.
    """
    entries = [_ca_entry(p, name) for p in certinfo.split_pem_bundle(pem)]
    if not entries:
        raise ValueError("Aucun certificat d'autorité trouvé dans le PEM fourni.")
    cfg = _read(db)
    existing = {c["id"] for c in cfg["cas"]}
    for e in entries:
        if e["id"] not in existing:
            cfg["cas"].append(e)
            existing.add(e["id"])
    _write(db, cfg)
    db.commit()
    trust.apply(_trust_pems(cfg))
    return status(db)


def remove_ca(db: Session, ca_id: str) -> dict:
    """Delete a CA from the store by id, withdrawing the trust immediately.

    Raises if the id is unknown.
    """
    cfg = _read(db)
    before = len(cfg["cas"])
    cfg["cas"] = [c for c in cfg["cas"] if c["id"] != ca_id]
    if len(cfg["cas"]) == before:
        raise ValueError("Autorité de certification introuvable.")
    _write(db, cfg)
    db.commit()
    trust.apply(_trust_pems(cfg))
    return status(db)


def status(db: Session) -> dict:
    """The store as the admin UI reads it. The PEM bodies stay out of the list;
    they are downloadable one by one through :func:`export_ca_pem`."""
    cas = [{k: v for k, v in c.items() if k != "pem"} for c in _read(db).get("cas", [])]
    return {
        "cas": cas,
        "roots": [c for c in cas if c["kind"] == "root"],
        "intermediates": [c for c in cas if c["kind"] == "intermediate"],
    }


def export_ca_pem(db: Session, ca_id: str) -> str:
    """Return a stored CA certificate's PEM for download (public material)."""
    for c in _read(db).get("cas", []):
        if c["id"] == ca_id:
            return c["pem"]
    raise ValueError("Autorité de certification introuvable.")
