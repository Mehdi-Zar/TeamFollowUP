"""SAML 2.0 SP-initiated flow (target IdP: PingFederate), configured at runtime.

python3-saml (and xmlsec) is imported lazily so the app boots fine when SAML is
disabled or native libs are unavailable.
"""
from typing import Any

from fastapi import Request


def saml_available() -> bool:
    """True if the native SAML stack (python3-saml/xmlsec) can be imported.

    Lets callers degrade gracefully when the optional native libs are absent
    instead of crashing the whole app at import time.
    """
    try:
        import onelogin.saml2.auth  # noqa: F401
        return True
    except Exception:
        return False


def _load_idp_metadata_settings(cfg: dict) -> dict[str, Any]:
    """Fetch and parse the IdP half of the SAML settings from URL or file.

    Prefers a remote metadata URL, falling back to a local metadata file, then to
    an empty IdP block. ``validate_cert=False`` on the remote fetch trusts the
    transport/network to the IdP metadata endpoint (see deployment docs).
    """
    from onelogin.saml2.idp_metadata_parser import OneLogin_Saml2_IdPMetadataParser

    if cfg.get("saml_idp_metadata_url"):
        return OneLogin_Saml2_IdPMetadataParser.parse_remote(cfg["saml_idp_metadata_url"], validate_cert=False)
    if cfg.get("saml_idp_metadata_path"):
        with open(cfg["saml_idp_metadata_path"], "r", encoding="utf-8") as f:
            return OneLogin_Saml2_IdPMetadataParser.parse(f.read())
    return {"idp": {}}


def build_settings(cfg: dict) -> dict[str, Any]:
    """Assemble the full python3-saml settings dict (SP block + parsed IdP block).

    ``strict=True`` enforces spec-compliant response validation (signatures,
    conditions, timestamps). The SP entityId/ACS/cert/key come from the runtime
    auth config; the IdP section is merged in from its metadata.

    The merge is deliberately not a plain ``dict.update``. The metadata parser
    returns more than an ``idp`` block: it also emits an ``sp`` hint (a
    ``NameIDFormat`` read from the IdP descriptor) and a ``security`` block. A
    flat update would replace our whole ``sp`` section with that one-key hint,
    dropping entityId and the ACS URL, and python3-saml would then reject the
    settings with ``sp_entityId_not_found,sp_acs_not_found``. Keycloak and
    PingFederate both advertise a NameIDFormat, so this affects real IdPs.
    """
    parsed = _load_idp_metadata_settings(cfg)
    sp_cert = cfg.get("saml_sp_cert") or ""
    sp_key = cfg.get("saml_sp_key") or ""
    out: dict[str, Any] = {
        "strict": True,
        "debug": False,
        "sp": {
            "entityId": cfg.get("saml_sp_entity_id"),
            "assertionConsumerService": {
                "url": cfg.get("saml_acs_url"),
                "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST",
            },
            "NameIDFormat": "urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress",
            "x509cert": sp_cert,
            "privateKey": sp_key,
        },
    }
    for key, value in (parsed or {}).items():
        if key == "sp" and isinstance(value, dict):
            # Keep every value we set ourselves; take the rest as a suggestion.
            for sub_key, sub_value in value.items():
                out["sp"].setdefault(sub_key, sub_value)
        elif key == "security" and isinstance(value, dict):
            security = dict(value)
            # The IdP may advertise that it wants signed AuthnRequests. We can
            # only honour that with a key pair; without one, signing is left off
            # rather than failing to build the settings at all. An IdP that truly
            # requires the signature will reject the request, which is the right
            # place for that error to surface.
            if security.get("authnRequestsSigned") and not (sp_cert and sp_key):
                security["authnRequestsSigned"] = False
            out["security"] = {**out.get("security", {}), **security}
        else:
            out[key] = value
    return out


async def _prepare_request(request: Request, cfg: dict | None = None) -> dict[str, Any]:
    """Adapt a Starlette request into the dict python3-saml expects.

    Maps scheme/host/port/path/query/form into the library's request shape. Strict
    mode checks the assertion's Destination against the URL rebuilt from this dict,
    so it has to be the **public** URL, not the pod's internal one. The configured
    public base URL wins when there is one; otherwise the (proxy-corrected) request
    URL is used, which already honours X-Forwarded-Proto / -Host.
    """
    from urllib.parse import urlsplit

    form = {}
    if request.method == "POST":
        form = dict(await request.form())
    url = request.url
    base = (cfg or {}).get("base_url_effective") or ""
    if base:
        parts = urlsplit(base)
        scheme, host, port = parts.scheme, parts.hostname, parts.port
    else:
        scheme, host, port = url.scheme, url.hostname, url.port
    return {
        "https": "on" if scheme == "https" else "off",
        "http_host": host or "localhost",
        "server_port": str(port or (443 if scheme == "https" else 80)),
        "script_name": url.path,
        "get_data": dict(request.query_params),
        "post_data": form,
    }


async def make_auth(request: Request, cfg: dict):
    """Build the per-request SAML auth object used to start login or verify a
    response. Instantiated fresh each call from the current request + runtime config."""
    from onelogin.saml2.auth import OneLogin_Saml2_Auth

    req = await _prepare_request(request, cfg)
    return OneLogin_Saml2_Auth(req, build_settings(cfg))
