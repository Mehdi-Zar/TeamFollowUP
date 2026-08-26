"""Connectivity and configuration checks against a configured IdP.

Answers the question an administrator actually has before rolling SSO out: "is
what I just typed going to work?", without asking a real user to attempt a login.
Each provider returns an ordered list of checks so the failure is pinpointed
rather than reported as a bare "connection failed".

Nothing here mutates state. Outbound calls go to URLs the administrator supplied,
which is the same trust level as the login path itself (only an admin can set an
issuer or a metadata URL, and the app already fetches both during a real login).
Timeouts are short so a wrong host fails fast instead of hanging the screen.
"""
from __future__ import annotations

from typing import Any

TIMEOUT = 8.0


def _check(label: str, ok: bool, detail: str = "", level: str = "") -> dict[str, Any]:
    """One line of the report. ``level='warn'`` marks something worth knowing that
    is not a failure, so a warning never makes the whole test red."""
    return {"label": label, "ok": bool(ok), "detail": str(detail), "level": level or ("ok" if ok else "error")}


def _result(provider: str, checks: list[dict], hint: str = "") -> dict[str, Any]:
    failed = [c for c in checks if not c["ok"] and c["level"] != "warn"]
    return {
        "provider": provider,
        "ok": not failed,
        "checks": checks,
        "hint": hint or (failed[0]["label"] if failed else ""),
    }


# --------------------------------------------------------------------- OIDC ---

def test_oidc(cfg: dict) -> dict[str, Any]:
    """Walk the OIDC discovery chain, then probe the client credentials.

    The credential probe is an ``authorization_code`` token request carrying a
    deliberately bogus code. Client authentication is evaluated *before* the grant
    itself, so the two answers separate cleanly: ``invalid_client`` (or 401) means
    the id/secret are wrong, while ``invalid_grant`` means the credentials were
    accepted and only the fake code was rejected, which is exactly what we want.

    A ``client_credentials`` probe was tried first and is not usable: Keycloak
    checks whether the grant is enabled before checking the secret, so it answers
    ``unauthorized_client`` even when the secret is wrong. Nothing is consumed by
    the bogus code, and no user interaction is needed.
    """
    import httpx

    checks: list[dict] = []
    issuer = (cfg.get("oidc_issuer_url") or "").strip().rstrip("/")
    client_id = (cfg.get("oidc_client_id") or "").strip()
    client_secret = cfg.get("oidc_client_secret") or ""

    if not issuer:
        return _result("oidc", [_check("URL de l'émetteur (issuer)", False, "Non renseignée")])
    checks.append(_check("URL de l'émetteur (issuer)", True, issuer))

    well_known = f"{issuer}/.well-known/openid-configuration"
    try:
        with httpx.Client(timeout=TIMEOUT, follow_redirects=True) as client:
            resp = client.get(well_known)
    except Exception as exc:
        return _result("oidc", checks + [
            _check("Document de découverte", False, f"{type(exc).__name__}: {exc}"),
        ], "L'émetteur n'est pas joignable depuis le serveur de l'application.")

    if resp.status_code != 200:
        return _result("oidc", checks + [
            _check("Document de découverte", False, f"HTTP {resp.status_code} sur {well_known}"),
        ], "L'URL de l'émetteur ne sert pas de document de découverte OpenID.")
    try:
        doc = resp.json()
    except Exception:
        return _result("oidc", checks + [_check("Document de découverte", False, "Réponse non JSON")])
    checks.append(_check("Document de découverte", True, f"HTTP 200, {len(doc)} entrées"))

    declared = (doc.get("issuer") or "").rstrip("/")
    checks.append(_check(
        "Émetteur annoncé cohérent", declared == issuer,
        declared or "absent",
        "" if declared == issuer else "error",
    ))

    for key, label in (("authorization_endpoint", "Point d'autorisation"),
                       ("token_endpoint", "Point de jeton"),
                       ("jwks_uri", "Clés publiques (JWKS)")):
        checks.append(_check(label, bool(doc.get(key)), doc.get(key) or "absent"))

    # PKCE: the app always sends S256, so an IdP that does not advertise it is
    # worth flagging, without failing the test (many IdPs support it silently).
    methods = doc.get("code_challenge_methods_supported") or []
    checks.append(_check("PKCE S256 annoncé", "S256" in methods,
                         ", ".join(methods) or "non annoncé",
                         "ok" if "S256" in methods else "warn"))

    jwks_uri = doc.get("jwks_uri")
    if jwks_uri:
        try:
            with httpx.Client(timeout=TIMEOUT, follow_redirects=True) as client:
                jwks = client.get(jwks_uri)
            keys = (jwks.json() or {}).get("keys") or []
            checks.append(_check("Clés de signature récupérées", bool(keys), f"{len(keys)} clé(s)"))
        except Exception as exc:
            checks.append(_check("Clés de signature récupérées", False, f"{type(exc).__name__}: {exc}"))

    if not client_id:
        checks.append(_check("Identifiants du client", False, "Client ID non renseigné"))
        return _result("oidc", checks)

    token_endpoint = doc.get("token_endpoint")
    if token_endpoint:
        try:
            with httpx.Client(timeout=TIMEOUT, follow_redirects=True) as client:
                probe = client.post(token_endpoint, data={
                    "grant_type": "authorization_code",
                    "code": "teamfollowup-connectivity-probe",
                    "redirect_uri": cfg.get("oidc_redirect_uri") or "",
                }, auth=(client_id, client_secret))
            body = {}
            try:
                body = probe.json() or {}
            except Exception:
                pass
            err = body.get("error", "")
            if err == "invalid_client" or probe.status_code == 401:
                checks.append(_check("Identifiants du client", False,
                                     "Refusés par l'IdP : vérifiez le client ID et le secret"))
            elif err == "invalid_grant" or probe.status_code == 200:
                checks.append(_check("Identifiants du client", True,
                                     "Acceptés (le code de test est rejeté, ce qui est attendu)"))
            elif err in ("unauthorized_client", "unsupported_grant_type"):
                checks.append(_check("Identifiants du client", False,
                                     f"Le flux « code d'autorisation » semble désactivé pour ce client ({err})"))
            else:
                checks.append(_check("Identifiants du client", True,
                                     f"Réponse ambiguë (HTTP {probe.status_code} {err}), à confirmer par une vraie connexion",
                                     "warn"))
        except Exception as exc:
            checks.append(_check("Identifiants du client", False, f"{type(exc).__name__}: {exc}"))

    checks.append(_check("URL de redirection à déclarer chez l'IdP", True,
                         cfg.get("oidc_redirect_uri") or "non dérivée"))
    return _result("oidc", checks)


# --------------------------------------------------------------------- SAML ---

def test_saml(cfg: dict) -> dict[str, Any]:
    """Fetch and parse the IdP metadata, then build the SP settings for real.

    The last step is the valuable one: it runs the same assembly the login flow
    runs and asks python3-saml to validate it. A settings problem therefore shows
    up here, on a button, instead of as a 500 during someone's first login.
    """
    from .saml import saml_available

    checks: list[dict] = []
    if not saml_available():
        return _result("saml", [_check("Bibliothèque SAML disponible", False,
                                       "python3-saml / xmlsec absent de cette image")])
    checks.append(_check("Bibliothèque SAML disponible", True, "python3-saml + xmlsec"))

    url = (cfg.get("saml_idp_metadata_url") or "").strip()
    path = (cfg.get("saml_idp_metadata_path") or "").strip()
    if not url and not path:
        return _result("saml", checks + [
            _check("Source des métadonnées IdP", False, "Ni URL ni fichier renseignés")])
    checks.append(_check("Source des métadonnées IdP", True, url or path))

    from .saml import _load_idp_metadata_settings, build_settings
    try:
        parsed = _load_idp_metadata_settings(cfg)
    except Exception as exc:
        return _result("saml", checks + [
            _check("Métadonnées IdP lues", False, f"{type(exc).__name__}: {exc}")],
            "Les métadonnées de l'IdP n'ont pas pu être récupérées ou analysées.")

    idp = (parsed or {}).get("idp") or {}
    checks.append(_check("Métadonnées IdP lues", bool(idp), f"{len(parsed or {})} bloc(s)"))
    checks.append(_check("Entity ID de l'IdP", bool(idp.get("entityId")), idp.get("entityId") or "absent"))

    sso = idp.get("singleSignOnService") or {}
    checks.append(_check("Point d'entrée SSO", bool(sso.get("url")),
                         f"{sso.get('url', 'absent')} ({(sso.get('binding') or '').rsplit(':', 1)[-1]})"))

    cert = idp.get("x509cert") or (idp.get("x509certMulti") or {}).get("signing")
    checks.append(_check("Certificat de signature de l'IdP", bool(cert),
                         _cert_summary(cert) if cert else "absent"))

    # The real assembly, validated exactly as the login path would do it.
    try:
        from onelogin.saml2.settings import OneLogin_Saml2_Settings
        settings_dict = build_settings(cfg)
        OneLogin_Saml2_Settings(settings_dict, sp_validation_only=True)
        checks.append(_check("Configuration du fournisseur de service (SP)", True, "Validée par python3-saml"))
        sp = settings_dict.get("sp") or {}
        checks.append(_check("Entity ID à déclarer chez l'IdP", True, sp.get("entityId") or "non dérivé"))
        checks.append(_check("URL ACS à déclarer chez l'IdP", True,
                             (sp.get("assertionConsumerService") or {}).get("url") or "non dérivée"))
    except Exception as exc:
        checks.append(_check("Configuration du fournisseur de service (SP)", False, str(exc)))
        return _result("saml", checks, "La configuration SP est refusée par la bibliothèque SAML.")

    return _result("saml", checks)


def _cert_summary(cert: str) -> str:
    """Subject and expiry of the IdP signing certificate, best effort.

    An expired IdP certificate is a classic silent SAML breakage, so surfacing the
    date here is worth the parsing attempt; failing to parse is not an error.
    """
    try:
        import base64
        from cryptography import x509

        der = base64.b64decode("".join(cert.split()))
        parsed = x509.load_der_x509_certificate(der)
        return f"expire le {parsed.not_valid_after_utc:%d/%m/%Y}"
    except Exception:
        return f"{len(cert)} caractères"
