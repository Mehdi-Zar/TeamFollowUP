"""SAML 2.0 SP-initiated flow (target IdP: PingFederate), configured at runtime.

python3-saml (and xmlsec) is imported lazily so the app boots fine when SAML is
disabled or native libs are unavailable.
"""
from typing import Any

from fastapi import Request


def saml_available() -> bool:
    try:
        import onelogin.saml2.auth  # noqa: F401
        return True
    except Exception:
        return False


def _load_idp_metadata_settings(cfg: dict) -> dict[str, Any]:
    from onelogin.saml2.idp_metadata_parser import OneLogin_Saml2_IdPMetadataParser

    if cfg.get("saml_idp_metadata_url"):
        return OneLogin_Saml2_IdPMetadataParser.parse_remote(cfg["saml_idp_metadata_url"], validate_cert=False)
    if cfg.get("saml_idp_metadata_path"):
        with open(cfg["saml_idp_metadata_path"], "r", encoding="utf-8") as f:
            return OneLogin_Saml2_IdPMetadataParser.parse(f.read())
    return {"idp": {}}


def build_settings(cfg: dict) -> dict[str, Any]:
    idp = _load_idp_metadata_settings(cfg)
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
            "x509cert": cfg.get("saml_sp_cert") or "",
            "privateKey": cfg.get("saml_sp_key") or "",
        },
    }
    out.update(idp)
    return out


async def _prepare_request(request: Request) -> dict[str, Any]:
    form = {}
    if request.method == "POST":
        form = dict(await request.form())
    url = request.url
    return {
        "https": "on" if url.scheme == "https" else "off",
        "http_host": url.hostname or "localhost",
        "server_port": str(url.port or (443 if url.scheme == "https" else 80)),
        "script_name": url.path,
        "get_data": dict(request.query_params),
        "post_data": form,
    }


async def make_auth(request: Request, cfg: dict):
    from onelogin.saml2.auth import OneLogin_Saml2_Auth

    req = await _prepare_request(request)
    return OneLogin_Saml2_Auth(req, build_settings(cfg))
