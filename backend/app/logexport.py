"""Send audit-log entries to an external destination (syslog / GCS / BigQuery).

Syslog uses the stdlib. For the two Google destinations, the **data-plane** calls
(GCS upload, BigQuery ``insertAll``) are plain httpx REST calls, but the **token**
is obtained through ``google-auth`` so we support Google's recommended, keyless
authentication order (see ``logexportconfig`` docstring): attached service account
(ADC), Workload Identity Federation, impersonation, and - last - a JSON key. The
token endpoints (metadata server, STS, IAM Credentials) are driven over the same
httpx client via a small transport adapter, so we keep a single HTTP client.
"""
from __future__ import annotations

import json
import socket
from datetime import datetime

import google.auth
import httpx
from google.auth import impersonated_credentials
from google.auth.exceptions import DefaultCredentialsError
from google.auth.transport import Request as _AuthRequest
from google.oauth2 import service_account
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import AuditLog, User

DEFAULT_UNIVERSE = "googleapis.com"
# OAuth scopes are universe-independent identifiers (NOT endpoints), kept as-is.
SCOPE_GCS = "https://www.googleapis.com/auth/devstorage.read_write"
SCOPE_BQ = "https://www.googleapis.com/auth/bigquery.insertdata"
# Base scope a source identity needs to mint impersonated tokens.
SCOPE_CLOUD_PLATFORM = "https://www.googleapis.com/auth/cloud-platform"

# RFC 5424 severity/facility for an informational app log: local0.info -> 16*8+6
SYSLOG_PRI = 134


def _universe_from(cfg: dict, creds) -> str:
    """Resolve the Google Cloud universe domain.

    Precedence: explicit admin config > the credentials' `universe_domain`
    (google-auth reads it from the metadata server / key / WIF config) > the
    public Google Cloud default (`googleapis.com`). For S3NS / Cloud de Confiance
    this is `s3nsapis.fr`, so endpoints become e.g. `storage.s3nsapis.fr`.
    """
    return (
        (cfg.get("universe_domain") or "").strip()
        or (getattr(creds, "universe_domain", "") or "").strip()
        or DEFAULT_UNIVERSE
    )


def _service_endpoint(service: str, universe: str) -> str:
    """e.g. ("storage", "s3nsapis.fr") -> "https://storage.s3nsapis.fr"."""
    return f"https://{service}.{universe}"


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
# Google Cloud auth (keyless-first, via google-auth over our httpx client)
# --------------------------------------------------------------------------- #
class _HttpxAuthResponse:
    """Adapts an httpx.Response to google.auth.transport.Response."""

    def __init__(self, resp: httpx.Response):
        self.status = resp.status_code
        self.headers = resp.headers
        self.data = resp.content


class _HttpxAuthRequest(_AuthRequest):
    """A google.auth transport backed by httpx, so token acquisition (metadata
    server, STS, IAM Credentials) uses the same HTTP client as the data plane."""

    def __call__(self, url, method="GET", body=None, headers=None, timeout=None, **kwargs):
        resp = httpx.request(method, url, content=body, headers=headers, timeout=timeout or 30)
        return _HttpxAuthResponse(resp)


def _load_key_info(cfg: dict) -> dict:
    raw = cfg.get("gcp_credentials_json") or ""
    if not raw.strip():
        raise LogExportError("Clé de compte de service Google manquante.")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        raise LogExportError("La clé de compte de service n'est pas un JSON valide.")


def _base_credentials(cfg: dict, scopes: list[str]):
    """Build the base Google credentials per the configured auth_method."""
    method = cfg.get("auth_method", "adc")
    impersonate = (cfg.get("impersonate_service_account") or "").strip()
    if method == "key":
        try:
            return service_account.Credentials.from_service_account_info(
                _load_key_info(cfg), scopes=scopes)
        except LogExportError:
            raise
        except Exception as e:
            raise LogExportError(f"Clé de compte de service invalide: {e}")
    if method == "wif":
        raw = cfg.get("wif_config_json") or ""
        if not raw.strip():
            raise LogExportError("Configuration Workload Identity Federation manquante.")
        try:
            info = json.loads(raw)
        except json.JSONDecodeError:
            raise LogExportError("La configuration WIF n'est pas un JSON valide.")
        try:
            creds, _ = google.auth.load_credentials_from_dict(info, scopes=scopes)
            return creds
        except Exception as e:
            raise LogExportError(f"Configuration WIF invalide: {e}")
    # "adc" or "impersonation": the base identity is Application Default
    # Credentials (attached service account on GKE/Cloud Run/GCE, GOOGLE_
    # APPLICATION_CREDENTIALS elsewhere). To later impersonate, the base must
    # carry the broad cloud-platform scope.
    base_scopes = [SCOPE_CLOUD_PLATFORM] if (method == "impersonation" or impersonate) else scopes
    try:
        creds, _ = google.auth.default(scopes=base_scopes)
        return creds
    except DefaultCredentialsError as e:
        raise LogExportError(
            "Aucune identité Google détectée (Application Default Credentials). "
            "Sur GKE/Cloud Run, attachez un compte de service au pod (Workload "
            f"Identity for GKE). Détail: {e}")


def _credentials(cfg: dict, scopes: list[str]):
    """Base credentials, optionally wrapped in service-account impersonation."""
    base = _base_credentials(cfg, scopes)
    method = cfg.get("auth_method", "adc")
    impersonate = (cfg.get("impersonate_service_account") or "").strip()
    if method != "impersonation" and not impersonate:
        return base
    if not impersonate:
        raise LogExportError("Compte de service à emprunter (impersonation) manquant.")
    # Honour the universe for the IAM Credentials endpoint (S3NS uses its own).
    universe = _universe_from(cfg, base)
    override = None
    if universe and universe != DEFAULT_UNIVERSE:
        override = (f"https://iamcredentials.{universe}"
                    "/v1/projects/-/serviceAccounts/{}:generateAccessToken")
    return impersonated_credentials.Credentials(
        source_credentials=base,
        target_principal=impersonate,
        target_scopes=scopes,
        lifetime=3600,
        iam_endpoint_override=override,
    )


def _token_and_universe(cfg: dict, scope: str) -> tuple[str, str]:
    """Return a fresh OAuth bearer token and the resolved universe domain."""
    creds = _credentials(cfg, [scope])
    try:
        creds.refresh(_HttpxAuthRequest())
    except LogExportError:
        raise
    except Exception as e:
        raise LogExportError(f"Échec de l'authentification Google: {type(e).__name__}: {e}")
    return creds.token, _universe_from(cfg, creds)


# --------------------------------------------------------------------------- #
# GCS
# --------------------------------------------------------------------------- #
def _upload_gcs(cfg: dict, entries: list[dict]) -> tuple[bool, str]:
    bucket = (cfg.get("gcs_bucket") or "").strip()
    prefix = (cfg.get("gcs_prefix") or "").strip().strip("/")
    if not bucket:
        raise LogExportError("Nom du bucket GCS manquant.")
    token, universe = _token_and_universe(cfg, SCOPE_GCS)

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
    token, universe = _token_and_universe(cfg, SCOPE_BQ)

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
