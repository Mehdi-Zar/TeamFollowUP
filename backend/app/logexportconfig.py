"""Log/audit export configuration stored in DB, editable from the admin UI (like SMTP).

Supports three destinations:
  - syslog   : RFC 3164/5424 over UDP or TCP (e.g. rsyslog, Graylog, Datadog agent)
  - gcs      : append newline-delimited JSON objects to a Google Cloud Storage bucket
  - bigquery : stream rows into a BigQuery table (tabledata.insertAll)

For the two Google destinations, authentication follows Google's recommended
order (keyless first, key last) via ``auth_method``:
  - adc           : Application Default Credentials - the attached service account
                    (Workload Identity Federation for GKE / GCE / Cloud Run). No
                    secret stored anywhere. **Default and recommended.**
  - wif           : Workload Identity Federation with an external identity provider,
                    configured by an ``external_account`` credential file (NOT a key).
                    For workloads running OFF Google Cloud (VMware/on-prem, other cloud).
  - impersonation : take a base identity (ADC) and impersonate a target service
                    account via the IAM Credentials API (least privilege / cross-project).
  - key           : a downloaded service-account JSON key. Long-lived secret - a
                    last-resort fallback that Google recommends disabling org-wide
                    (`iam.disableServiceAccountKeyCreation`). Kept for compatibility.
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

        # Google Cloud universe domain. Empty = auto (read from the credentials,
        # else "googleapis.com"). For S3NS / Cloud de Confiance: "s3nsapis.fr".
        "universe_domain": "",

        # --- Google authentication (see module docstring) ---
        # "adc" | "wif" | "impersonation" | "key"
        "auth_method": "adc",
        # Optional target service account to impersonate. Required for the
        # "impersonation" method; may also refine "adc"/"wif" (act-as another SA).
        "impersonate_service_account": "",
        # external_account credential config JSON for the "wif" method (safe to
        # store - it is a config file, not a secret key).
        "wif_config_json": "",
        # Service-account key JSON for the "key" method (GCS and BigQuery). Secret.
        "gcp_credentials_json": "",
    }


KEYS = set(_defaults().keys())
VALID_AUTH_METHODS = ("adc", "wif", "impersonation", "key")
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
    if cfg.get("auth_method") not in VALID_AUTH_METHODS:
        cfg["auth_method"] = "adc"

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
