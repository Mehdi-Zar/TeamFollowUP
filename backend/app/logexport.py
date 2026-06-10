"""Send audit-log entries to an external destination (syslog / GCS / BigQuery).

Kept dependency-light on purpose: syslog uses the stdlib, while GCS and BigQuery
talk to the Google REST APIs directly using a service-account JWT (PyJWT + httpx),
so no google-cloud SDK is required.
"""
from __future__ import annotations

import json
import socket
import time
from datetime import datetime

import httpx
import jwt
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import AuditLog, User

DEFAULT_UNIVERSE = "googleapis.com"
# OAuth scopes are universe-independent identifiers (NOT endpoints), kept as-is.
SCOPE_GCS = "https://www.googleapis.com/auth/devstorage.read_write"
SCOPE_BQ = "https://www.googleapis.com/auth/bigquery.insertdata"

# RFC 5424 severity/facility for an informational app log: local0.info -> 16*8+6
SYSLOG_PRI = 134


def _universe_domain(cfg: dict, creds: dict) -> str:
    """Resolve the Google Cloud universe domain.

    Precedence: explicit admin config > the service-account key's
    `universe_domain` > the public Google Cloud default (`googleapis.com`).
    For S3NS / Cloud de Confiance this is `s3nsapis.fr`, so endpoints become
    e.g. `storage.s3nsapis.fr` instead of `storage.googleapis.com`.
    """
    return (
        (cfg.get("universe_domain") or "").strip()
        or (creds.get("universe_domain") or "").strip()
        or DEFAULT_UNIVERSE
    )


def _service_endpoint(service: str, universe: str) -> str:
    """e.g. ("storage", "s3nsapis.fr") -> "https://storage.s3nsapis.fr"."""
    return f"https://{service}.{universe}"


def _token_endpoint(creds: dict, universe: str) -> str:
    # A key issued for a given universe already carries the right token_uri;
    # honour it, otherwise build it from the universe domain.
    return creds.get("token_uri") or f"https://oauth2.{universe}/token"


class LogExportError(Exception):
    pass


# --------------------------------------------------------------------------- #
# Serialization
# --------------------------------------------------------------------------- #
def serialize_entries(db: Session, limit: int = 200) -> list[dict]:
    """Most recent audit entries as plain dicts, oldest first."""
    rows = db.scalars(
        select(AuditLog).order_by(AuditLog.timestamp.desc()).limit(limit)
    ).all()
    emails = {
        u.id: u.email
        for u in db.scalars(select(User)).all()
    }
    out = []
    for r in reversed(list(rows)):
        out.append({
            "id": r.id,
            "timestamp": r.timestamp.isoformat() if isinstance(r.timestamp, datetime) else str(r.timestamp),
            "user_id": r.user_id,
            "user_email": emails.get(r.user_id),
            "action": r.action,
            "entity": r.entity,
            "entity_id": r.entity_id,
            "detail": r.detail,
        })
    return out


def sample_entry() -> dict:
    return {
        "id": 0,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "user_id": None,
        "user_email": "test@local",
        "action": "log_export.test",
        "entity": "log_export",
        "entity_id": None,
        "detail": {"message": "Tribe Cockpit log export test event"},
    }


# --------------------------------------------------------------------------- #
# Public entry point
# --------------------------------------------------------------------------- #
def export_entries(cfg: dict, entries: list[dict]) -> tuple[bool, str]:
    """Dispatch to the configured destination. Returns (ok, human message)."""
    dest = cfg.get("destination", "syslog")
    if not entries:
        return True, "Aucune entrée à exporter."
    try:
        if dest == "syslog":
            return _send_syslog(cfg, entries)
        if dest == "gcs":
            return _upload_gcs(cfg, entries)
        if dest == "bigquery":
            return _insert_bigquery(cfg, entries)
        return False, f"Destination inconnue: {dest}"
    except LogExportError as e:
        return False, str(e)
    except Exception as e:  # pragma: no cover - defensive
        return False, f"{type(e).__name__}: {e}"


# --------------------------------------------------------------------------- #
# syslog
# --------------------------------------------------------------------------- #
def _send_syslog(cfg: dict, entries: list[dict]) -> tuple[bool, str]:
    host = (cfg.get("syslog_host") or "").strip()
    port = int(cfg.get("syslog_port") or 514)
    proto = cfg.get("syslog_protocol", "udp")
    app_name = (cfg.get("syslog_app_name") or "tribe-cockpit").strip()
    if not host:
        raise LogExportError("Hôte syslog manquant.")

    hostname = socket.gethostname()
    messages = []
    for e in entries:
        ts = e.get("timestamp") or ""
        payload = json.dumps(e, ensure_ascii=False, default=str)
        # RFC 5424-ish: <PRI>1 TIMESTAMP HOST APP - - - MSG
        messages.append(f"<{SYSLOG_PRI}>1 {ts} {hostname} {app_name} - - - {payload}")

    if proto == "tcp":
        with socket.create_connection((host, port), timeout=10) as s:
            for m in messages:
                # octet-counting framing (RFC 6587) is the safest for TCP syslog
                frame = f"{len(m.encode('utf-8'))} {m}".encode("utf-8")
                s.sendall(frame)
    else:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.settimeout(10)
            for m in messages:
                s.sendto(m.encode("utf-8"), (host, port))
    return True, f"{len(messages)} entrée(s) envoyée(s) vers syslog {host}:{port} ({proto.upper()})."


# --------------------------------------------------------------------------- #
# Google Cloud auth
# --------------------------------------------------------------------------- #
def _load_credentials(cfg: dict) -> dict:
    raw = cfg.get("gcp_credentials_json") or ""
    if not raw.strip():
        raise LogExportError("Clé de compte de service Google manquante.")
    try:
        creds = json.loads(raw)
    except json.JSONDecodeError:
        raise LogExportError("La clé de compte de service n'est pas un JSON valide.")
    for field in ("client_email", "private_key", "token_uri"):
        if not creds.get(field):
            raise LogExportError(f"Clé de compte de service incomplète (champ « {field} » manquant).")
    return creds


def _access_token(creds: dict, scope: str, token_uri: str) -> str:
    now = int(time.time())
    claim = {
        "iss": creds["client_email"],
        "scope": scope,
        "aud": token_uri,
        "iat": now,
        "exp": now + 3600,
    }
    try:
        assertion = jwt.encode(claim, creds["private_key"], algorithm="RS256")
    except Exception as e:
        raise LogExportError(f"Impossible de signer le jeton (clé privée invalide ?): {e}")
    resp = httpx.post(
        token_uri,
        data={
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
            "assertion": assertion,
        },
        timeout=20,
    )
    if resp.status_code != 200:
        raise LogExportError(f"Échec de l'authentification ({resp.status_code}): {resp.text[:200]}")
    return resp.json()["access_token"]


# --------------------------------------------------------------------------- #
# GCS
# --------------------------------------------------------------------------- #
def _upload_gcs(cfg: dict, entries: list[dict]) -> tuple[bool, str]:
    bucket = (cfg.get("gcs_bucket") or "").strip()
    prefix = (cfg.get("gcs_prefix") or "").strip().strip("/")
    if not bucket:
        raise LogExportError("Nom du bucket GCS manquant.")
    creds = _load_credentials(cfg)
    universe = _universe_domain(cfg, creds)
    token = _access_token(creds, SCOPE_GCS, _token_endpoint(creds, universe))

    ndjson = "\n".join(json.dumps(e, ensure_ascii=False, default=str) for e in entries) + "\n"
    stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    name = f"{prefix + '/' if prefix else ''}audit-{stamp}.ndjson"

    resp = httpx.post(
        f"{_service_endpoint('storage', universe)}/upload/storage/v1/b/{bucket}/o",
        params={"uploadType": "media", "name": name},
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/x-ndjson"},
        content=ndjson.encode("utf-8"),
        timeout=30,
    )
    if resp.status_code not in (200, 201):
        raise LogExportError(f"Échec de l'envoi GCS ({resp.status_code}): {resp.text[:200]}")
    return True, f"{len(entries)} entrée(s) écrite(s) dans gs://{bucket}/{name} (univers {universe})."


# --------------------------------------------------------------------------- #
# BigQuery
# --------------------------------------------------------------------------- #
def _insert_bigquery(cfg: dict, entries: list[dict]) -> tuple[bool, str]:
    project = (cfg.get("bq_project") or "").strip()
    dataset = (cfg.get("bq_dataset") or "").strip()
    table = (cfg.get("bq_table") or "").strip()
    if not (project and dataset and table):
        raise LogExportError("Projet, dataset et table BigQuery sont requis.")
    creds = _load_credentials(cfg)
    universe = _universe_domain(cfg, creds)
    token = _access_token(creds, SCOPE_BQ, _token_endpoint(creds, universe))

    rows = []
    for e in entries:
        row = dict(e)
        # BigQuery streaming expects scalar-friendly values; serialize detail as JSON string.
        if isinstance(row.get("detail"), (dict, list)):
            row["detail"] = json.dumps(row["detail"], ensure_ascii=False)
        insert_id = str(e.get("id")) if e.get("id") else None
        rows.append({"insertId": insert_id, "json": row} if insert_id else {"json": row})

    url = (
        f"{_service_endpoint('bigquery', universe)}/bigquery/v2/projects/{project}"
        f"/datasets/{dataset}/tables/{table}/insertAll"
    )
    resp = httpx.post(
        url,
        headers={"Authorization": f"Bearer {token}"},
        json={"kind": "bigquery#tableDataInsertAllRequest", "rows": rows},
        timeout=30,
    )
    if resp.status_code != 200:
        raise LogExportError(f"Échec BigQuery ({resp.status_code}): {resp.text[:200]}")
    body = resp.json()
    if body.get("insertErrors"):
        return False, f"BigQuery a refusé certaines lignes: {json.dumps(body['insertErrors'])[:200]}"
    return True, f"{len(rows)} ligne(s) insérée(s) dans {project}.{dataset}.{table} (univers {universe})."
