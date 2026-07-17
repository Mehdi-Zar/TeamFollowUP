# ADR-0012 - GCP authentication for log export: keyless by default

**Status:** Accepted · **Date:** 2026-07-17

## Context

The audit-log export (`logexport.py`) can ship to Google Cloud Storage or
BigQuery. The first implementation authenticated with a **single method**: a
service-account **JSON key** pasted into **Admin → Logs** and stored (masked) in
`app_settings`. The app signed a JWT with that key (PyJWT) and exchanged it for
an OAuth token.

A downloaded service-account key is a **long-lived secret**. Google's own IAM
guidance ranks it **last** among authentication options and recommends disabling
key creation org-wide (`iam.disableServiceAccountKeyCreation`, enforced by
default on Google Cloud organizations created after 2024-05-03). A key leaks, is
rarely rotated, and is the number-one target of repo scanners. Meanwhile the app
already runs on **GKE** (including S3NS GKE), where a **keyless** identity is
available at zero cost.

## Options Considered

1. **Keep the JSON key only.** Simplest, but institutionalizes the anti-pattern
   and cannot pass a security review that forbids downloaded keys.
2. **Attached service account / ADC only.** The gold standard on GKE, but leaves
   the non-GKE deploy target (VMware/on-prem, §4 of the deployment guide) with no
   Google auth at all.
3. **A method selector covering the full best-practice ladder**, defaulting to
   keyless, keeping the key as an explicit last resort. Chosen.

## Decision

**Offer Google's recommended methods in order, default to keyless, keep the key
as a labelled fallback.** `log_export.auth_method` ∈:

1. **`adc` (default, recommended).** Application Default Credentials via
   `google.auth.default()`. On GKE/Cloud Run/GCE this is the **attached service
   account** (Workload Identity Federation for GKE) resolved from the metadata
   server - **no secret stored anywhere**.
2. **`wif`.** Workload Identity Federation with an external IdP, configured by an
   `external_account` **config file** (not a key, no long-lived secret) - for
   workloads running **off** Google Cloud.
3. **`impersonation`.** A base ADC identity that impersonates a target service
   account via the IAM Credentials API (`generateAccessToken`) - least-privilege
   / cross-project.
4. **`key`.** The original JSON key. Kept for compatibility, shown behind an
   in-UI warning.

Supporting decisions:

- **`google-auth` owns token acquisition.** Re-implementing the STS and IAM
  Credentials token exchanges by hand is error-prone; the official library
  handles ADC, WIF, impersonation and the S3NS universe. It is the one new
  dependency.
- **One HTTP client.** The data-plane calls (GCS upload, BigQuery `insertAll`)
  stay plain httpx. `google-auth` is given a ~10-line httpx transport adapter
  (`_HttpxAuthRequest`) so token endpoints (metadata server, STS, IAM) also go
  through httpx - no `requests` dependency, no second client.
- **Universe-aware.** `universe_domain` (explicit config > credentials > default)
  still drives the storage/bigquery endpoints, and now the IAM Credentials
  endpoint too (`iamcredentials.s3nsapis.fr` for S3NS impersonation).
- **Optional impersonation on top of ADC/WIF.** `impersonate_service_account`
  can refine any base identity, not just the dedicated `impersonation` method.

## Rationale

The default is now the method a security review asks for, and the change is
config-only for existing key users (their `auth_method` stays `key`). The keyless
paths need **no secret in the database**, which removes the app from the blast
radius of a DB dump for those deployments.

## Consequences

- **Infra step for keyless:** on GKE the pod's Kubernetes ServiceAccount must be
  bound to a Google service account (Workload Identity). Documented in the
  deployment guide's IAM section.
- **New dependency:** `google-auth`. Offline tests mock it, so the suite stays
  network-free.
- **The key path is unchanged** functionally; only its UI placement (warning) and
  its plumbing (via `google-auth`) changed.

## Risks

- `google.auth.default()` failing off-GCP with `adc` selected yields a clear
  error pointing at Workload Identity - but an operator who picks `adc` on a
  non-GCP host will only find out at test/flush time.
- WIF misconfiguration is opaque (STS returns terse errors); the test button
  surfaces the raw message.

## Future Evolution

- Batching/retry and a dead-letter path for export failures (today it is
  best-effort, test/flush from the UI).
- Reuse this auth layer if other Google integrations appear (e.g. GCS-backed
  backups), rather than re-solving auth per feature.
