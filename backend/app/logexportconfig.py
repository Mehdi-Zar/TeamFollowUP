"""Log/audit export configuration stored in DB, editable from the admin UI (like SMTP).

Supports three destinations:
  - syslog   : RFC 3164/5424 over UDP or TCP (e.g. rsyslog, Graylog, Datadog agent)
  - gcs      : append newline-delimited JSON objects to a Google Cloud Storage bucket
  - bigquery : stream rows into a BigQuery table (tabledata.insertAll)
"""
import json

from sqlalchemy.orm import Session

from .models import AppSetting

LOG_EXPORT_KEY = "log_export"


def _defaults() -> dict:
    return {
        "enabled": False,
        # "syslog" | "gcs" | "bigquery"
        "destination": "syslog",

        # --- syslog ---
        "syslog_host": "",
        "syslog_port": 514,
        "syslog_protocol": "udp",      # "udp" | "tcp"
        "syslog_app_name": "tribe-cockpit",

        # --- Google Cloud Storage ---
        "gcs_bucket": "",
        "gcs_prefix": "audit-logs",    # object key prefix (folder)

        # --- BigQuery ---
        "bq_project": "",
        "bq_dataset": "",
        "bq_table": "audit_log",

        # Service-account key JSON, used for both GCS and BigQuery.
        "gcp_credentials_json": "",
    }


KEYS = set(_defaults().keys())
# Fields that should never be returned to the client in clear text.
SECRET_KEYS = {"gcp_credentials_json"}
INT_KEYS = {"syslog_port"}


def get_log_export(db: Session, *, reveal_secrets: bool = False) -> dict:
    cfg = _defaults()
    row = db.get(AppSetting, LOG_EXPORT_KEY)
    if row:
        try:
            cfg.update({k: v for k, v in json.loads(row.value).items() if k in KEYS})
        except (json.JSONDecodeError, TypeError):
            pass
    if not reveal_secrets:
        # Hide the raw credentials; expose only whether one is set.
        for k in SECRET_KEYS:
            cfg[f"{k}_set"] = bool(cfg.get(k))
            cfg[k] = ""
    return cfg


def set_log_export(db: Session, patch: dict) -> dict:
    cfg = get_log_export(db, reveal_secrets=True)
    for k, v in patch.items():
        if k not in KEYS:
            continue
        # An empty secret in the patch means "keep the existing value".
        if k in SECRET_KEYS and (v is None or v == ""):
            continue
        cfg[k] = v
    for k in INT_KEYS:
        try:
            cfg[k] = int(cfg[k])
        except (TypeError, ValueError):
            cfg[k] = _defaults()[k]
    if cfg.get("destination") not in ("syslog", "gcs", "bigquery"):
        cfg["destination"] = "syslog"
    if cfg.get("syslog_protocol") not in ("udp", "tcp"):
        cfg["syslog_protocol"] = "udp"

    row = db.get(AppSetting, LOG_EXPORT_KEY)
    payload = json.dumps(cfg)
    if row is None:
        db.add(AppSetting(key=LOG_EXPORT_KEY, value=payload))
    else:
        row.value = payload
    # Return the client-safe view (secrets masked).
    return _mask(cfg)


def _mask(cfg: dict) -> dict:
    out = dict(cfg)
    for k in SECRET_KEYS:
        out[f"{k}_set"] = bool(out.get(k))
        out[k] = ""
    return out
