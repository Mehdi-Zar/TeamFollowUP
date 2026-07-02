"""HTTPS/TLS configuration orchestration, DB-backed (AppSetting key ``tls``).

The DB blob is the single source of truth for the server certificate, its
private key and the admin-managed CA store. Any mutation persists to the DB,
re-materialises the PEM files on disk and hot-reloads the live SSLContext, so
uploaded certificates take effect immediately without restarting the container.

Out of the box (no blob yet) a self-signed certificate is generated so the site
is served over HTTPS from first boot.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from . import tls
from .models import AppSetting

log = logging.getLogger("trt.tls")

TLS_KEY = "tls"


def _defaults() -> dict:
    return {
        "mode": "self_signed",       # self_signed | custom
        "redirect_http": True,        # 301 plain HTTP -> HTTPS
        "self_signed": {},            # {cn, sans, generated_at}
        "leaf_cert_pem": "",          # active server certificate (PEM)
        "leaf_key_pem": "",           # active private key (PEM, unencrypted) - never exposed
        "bundled_chain_pem": "",      # intermediates that shipped with the leaf (PFX/PEM)
        "cas": [],                    # admin-managed CA store (root + intermediate)
    }


def _read(db: Session) -> dict:
    cfg = _defaults()
    row = db.get(AppSetting, TLS_KEY)
    if row:
        try:
            cfg.update({k: v for k, v in json.loads(row.value).items() if k in cfg})
        except (json.JSONDecodeError, TypeError):
            pass
    return cfg


def _write(db: Session, cfg: dict) -> None:
    row = db.get(AppSetting, TLS_KEY)
    payload = json.dumps(cfg)
    if row is None:
        db.add(AppSetting(key=TLS_KEY, value=payload))
    else:
        row.value = payload


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# CA-store helpers
# ---------------------------------------------------------------------------

def _ca_entry(pem: str, name: str | None) -> dict:
    """Build a CA-store record from a certificate PEM (raises on bad PEM)."""
    info = tls.cert_info(pem)
    return {
        "id": info["fingerprint_sha256"].replace(":", "")[:32].lower(),
        "name": name or info["subject"],
        "kind": tls.ca_kind(pem),
        "pem": tls.normalize_cert_pem(pem),
        "subject": info["subject"],
        "issuer": info["issuer"],
        "not_after": info["not_after"],
        "fingerprint": info["fingerprint_sha256"],
        "added_at": _now_iso(),
    }


# ---------------------------------------------------------------------------
# Materialisation
# ---------------------------------------------------------------------------

def _fullchain(cfg: dict) -> str:
    """Assemble leaf + bundled intermediates + store intermediates (deduped)."""
    parts = [cfg["leaf_cert_pem"].strip()]
    seen = {tls.cert_info(cfg["leaf_cert_pem"])["fingerprint_sha256"]}
    # Intermediates that came bundled with the leaf, then admin-managed ones.
    candidates: list[str] = []
    if cfg.get("bundled_chain_pem", "").strip():
        candidates.extend(tls.split_pem_bundle(cfg["bundled_chain_pem"]))
    candidates.extend(ca["pem"] for ca in cfg.get("cas", []) if ca.get("kind") == "intermediate")
    for pem in candidates:
        fp = tls.cert_info(pem)["fingerprint_sha256"]
        if fp not in seen:
            seen.add(fp)
            parts.append(pem.strip())
    return "\n".join(parts) + "\n"


def materialize(db: Session) -> None:
    """Write the active material to disk and hot-reload the live context."""
    cfg = _read(db)
    if not cfg.get("leaf_cert_pem") or not cfg.get("leaf_key_pem"):
        return
    tls.materialize(_fullchain(cfg), cfg["leaf_key_pem"])
    tls.reload_live_context()


def ensure_materialized(db: Session) -> dict:
    """Boot hook: create a self-signed cert if none exists, then write to disk.

    Returns the (public) status. Called by the server launcher *before* building
    the SSLContext so a certificate always exists.
    """
    cfg = _read(db)
    if not cfg.get("leaf_cert_pem") or not cfg.get("leaf_key_pem"):
        log.info("No TLS certificate configured - generating a self-signed one.")
        _apply_self_signed(db, cfg, cn="localhost", sans=["localhost", "127.0.0.1", "::1"])
        db.commit()
        cfg = _read(db)
    tls.materialize(_fullchain(cfg), cfg["leaf_key_pem"])
    return status(db)


# ---------------------------------------------------------------------------
# Mutations (each persists; caller commits + materialises)
# ---------------------------------------------------------------------------

def _apply_self_signed(db: Session, cfg: dict, cn: str, sans: list[str]) -> None:
    cert_pem, key_pem = tls.generate_self_signed(cn, sans)
    cfg["mode"] = "self_signed"
    cfg["leaf_cert_pem"] = cert_pem
    cfg["leaf_key_pem"] = key_pem
    cfg["bundled_chain_pem"] = ""
    cfg["self_signed"] = {"cn": cn, "sans": sans, "generated_at": _now_iso()}
    _write(db, cfg)


def regenerate_self_signed(db: Session, cn: str = "localhost", sans: list[str] | None = None) -> dict:
    cn = (cn or "localhost").strip()
    sans = [s.strip() for s in (sans or []) if s and s.strip()]
    if not sans:
        sans = [cn, "127.0.0.1", "::1"]
    cfg = _read(db)
    _apply_self_signed(db, cfg, cn, sans)
    db.commit()
    materialize(db)
    return status(db)


def import_pem(db: Session, cert_pem: str, key_pem: str, passphrase: str | None = None) -> dict:
    """Install a PEM certificate + private key. Extra certs in ``cert_pem`` are
    treated as the intermediate chain."""
    certs = tls.split_pem_bundle(cert_pem)
    if not certs:
        raise ValueError("Aucun certificat trouvé dans le PEM fourni.")
    leaf = certs[0]
    chain = "\n".join(certs[1:])
    key = tls.normalize_key_pem(key_pem, passphrase)
    if not tls.key_matches_cert(leaf, key):
        raise ValueError("La clé privée ne correspond pas au certificat.")
    cfg = _read(db)
    cfg["mode"] = "custom"
    cfg["leaf_cert_pem"] = leaf
    cfg["leaf_key_pem"] = key
    cfg["bundled_chain_pem"] = chain
    cfg["self_signed"] = {}
    _write(db, cfg)
    db.commit()
    materialize(db)
    return status(db)


def import_pfx(db: Session, data: bytes, password: str | None = None) -> dict:
    """Install a PKCS#12 (.pfx/.p12) bundle."""
    pfx = tls.load_pfx(data, password)
    if not tls.key_matches_cert(pfx.cert_pem, pfx.key_pem):
        raise ValueError("La clé privée du PFX ne correspond pas au certificat.")
    cfg = _read(db)
    cfg["mode"] = "custom"
    cfg["leaf_cert_pem"] = pfx.cert_pem
    cfg["leaf_key_pem"] = pfx.key_pem
    cfg["bundled_chain_pem"] = "\n".join(pfx.ca_pems)
    cfg["self_signed"] = {}
    _write(db, cfg)
    db.commit()
    materialize(db)
    return status(db)


def add_ca(db: Session, pem: str, name: str | None = None) -> dict:
    """Add one or more CA certificates (root and/or intermediate) to the store."""
    entries = [_ca_entry(p, name) for p in tls.split_pem_bundle(pem)]
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
    materialize(db)  # intermediates may extend the served chain
    return status(db)


def remove_ca(db: Session, ca_id: str) -> dict:
    cfg = _read(db)
    before = len(cfg["cas"])
    cfg["cas"] = [c for c in cfg["cas"] if c["id"] != ca_id]
    if len(cfg["cas"]) == before:
        raise ValueError("Autorité de certification introuvable.")
    _write(db, cfg)
    db.commit()
    materialize(db)
    return status(db)


def set_options(db: Session, patch: dict) -> dict:
    cfg = _read(db)
    if "redirect_http" in patch:
        cfg["redirect_http"] = bool(patch["redirect_http"])
    _write(db, cfg)
    db.commit()
    return status(db)


# ---------------------------------------------------------------------------
# Read models
# ---------------------------------------------------------------------------

def redirect_http_enabled(db: Session) -> bool:
    return bool(_read(db).get("redirect_http", True))


def status(db: Session) -> dict:
    """Non-secret status for the admin UI. Never returns the private key."""
    cfg = _read(db)
    active = None
    if cfg.get("leaf_cert_pem"):
        try:
            active = tls.cert_info(cfg["leaf_cert_pem"])
        except Exception as exc:  # corrupt cert - surface rather than crash
            active = {"error": str(exc)}
    cas = [
        {k: v for k, v in c.items() if k != "pem"}
        for c in cfg.get("cas", [])
    ]
    return {
        "mode": cfg.get("mode", "self_signed"),
        "redirect_http": bool(cfg.get("redirect_http", True)),
        "self_signed": cfg.get("self_signed", {}),
        "active": active,
        "chain_len": len(tls.split_pem_bundle(cfg["bundled_chain_pem"])) if cfg.get("bundled_chain_pem") else 0,
        "cas": cas,
        "roots": [c for c in cas if c["kind"] == "root"],
        "intermediates": [c for c in cas if c["kind"] == "intermediate"],
    }


def export_ca_pem(db: Session, ca_id: str) -> str:
    for c in _read(db).get("cas", []):
        if c["id"] == ca_id:
            return c["pem"]
    raise ValueError("Autorité de certification introuvable.")


def export_active_cert_pem(db: Session) -> str:
    """The active leaf certificate (public) - handy to trust a self-signed cert."""
    cfg = _read(db)
    if not cfg.get("leaf_cert_pem"):
        raise ValueError("Aucun certificat actif.")
    return cfg["leaf_cert_pem"]
