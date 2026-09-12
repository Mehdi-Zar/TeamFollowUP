"""L'ecran de connexion: ce qu'il propose, dans quel ordre, et ce qu'il cache.

Le probleme d'origine est un probleme d'usage, pas de securite: une organisation
qui se connecte par son IdP mais dont la page affiche un formulaire email et mot
de passe apprend le mauvais geste a chaque nouvel arrivant, qui reclame ensuite un
mot de passe que personne ne lui donnera.

Ce qui est teste ici est donc surtout ce que la page PUBLIQUE revele: les libelles
et les logos sont faits pour etre lus par n'importe qui, le jeton du lien de
secours ne doit jamais sortir, et masquer le formulaire ne doit jamais empecher le
compte de secours de se connecter.
"""
from app.authconfig import get_auth_config, login_screen, set_auth_config
from tests.conftest import login


def _configure(client, **patch):
    """Regle l'ecran de connexion en passant par l'API d'administration."""
    login(client, "admin@test")
    r = client.put("/api/admin/auth-config", json=patch)
    assert r.status_code == 200, r.text
    return r.json()


def _public(client, **params):
    client.cookies.clear()
    r = client.get("/api/auth/config", params=params)
    assert r.status_code == 200, r.text
    return r.json()


# ---- ordre et presentation ------------------------------------------------------

def test_the_page_lists_what_is_configured_in_the_chosen_order(client, db, seeded):
    _configure(client, oidc_enabled=True, oidc_issuer_url="https://idp.example",
               oidc_client_id="app", login_methods=[
                   {"key": "password", "order": 2, "enabled": True},
                   {"key": "oidc", "order": 1, "enabled": True, "primary": True,
                    "label": "Continuer avec le hub", "hint": "Compte de l'entreprise"},
               ])
    out = _public(client)
    assert [m["key"] for m in out["methods"]] == ["oidc", "password"]
    assert out["methods"][0]["label"] == "Continuer avec le hub"
    assert out["methods"][0]["hint"] == "Compte de l'entreprise"
    assert out["methods"][0]["primary"] is True
    assert out["methods"][1]["primary"] is False        # une seule principale


def test_a_method_that_is_not_configured_is_never_offered(client, db, seeded):
    """Un bouton qui mene a une page d'erreur est pire que pas de bouton."""
    _configure(client, oidc_enabled=False, saml_enabled=False,
               login_methods=[{"key": "oidc", "enabled": True},
                              {"key": "saml", "enabled": True}])
    out = _public(client)
    assert [m["key"] for m in out["methods"]] == ["password"]


def test_hiding_a_method_removes_it_from_the_page(client, db, seeded):
    _configure(client, oidc_enabled=True, oidc_issuer_url="https://idp.example",
               oidc_client_id="app",
               login_methods=[{"key": "oidc", "enabled": True},
                              {"key": "password", "enabled": False}])
    assert [m["key"] for m in _public(client)["methods"]] == ["oidc"]


def test_the_welcome_message_and_the_logo_reach_the_page(client, db, seeded):
    """Libelles et logo sont faits pour etre lus par n'importe qui: ils sortent."""
    logo = "data:image/png;base64,iVBORw0KGgo="
    _configure(client, oidc_enabled=True, oidc_issuer_url="https://idp.example",
               oidc_client_id="app", login_intro="Bienvenue chez nous",
               login_methods=[{"key": "oidc", "enabled": True, "logo": logo}])
    out = _public(client)
    assert out["intro"] == "Bienvenue chez nous"
    assert out["methods"][0]["logo"] == logo


def test_a_logo_that_would_bloat_every_read_is_capped(client, db, seeded):
    huge = "data:image/png;base64," + ("A" * 400_000)
    _configure(client, oidc_enabled=True, oidc_issuer_url="https://idp.example",
               oidc_client_id="app",
               login_methods=[{"key": "oidc", "enabled": True, "logo": huge}])
    assert len(_public(client)["methods"][0]["logo"]) <= 300_000


# ---- le formulaire local et le lien de secours ----------------------------------

def test_the_password_form_can_be_folded_away(client, db, seeded):
    out = _configure(client, password_mode="collapsed")
    assert out["password_mode"] == "collapsed"
    public = _public(client)
    assert public["password_mode"] == "collapsed"
    # Toujours annonce: la page le replie derriere un lien, elle ne le supprime pas.
    assert any(m["key"] == "password" for m in public["methods"])


def test_the_secret_mode_hides_the_form_and_never_leaks_its_token(client, db, seeded):
    out = _configure(client, password_mode="secret")
    token = out["password_secret"]
    assert token, "un jeton doit etre genere plutot que demande"

    public = _public(client)
    assert public["password_mode"] == "secret"
    assert all(m["key"] != "password" for m in public["methods"])
    assert token not in str(public)                    # le jeton ne sort jamais

    unlocked = _public(client, k=token)
    assert unlocked["password_mode"] == "visible"
    assert any(m["key"] == "password" for m in unlocked["methods"])


def test_a_wrong_token_says_nothing_more_than_a_wrong_password(client, db, seeded):
    _configure(client, password_mode="secret")
    out = _public(client, k="pas-le-bon-jeton")
    assert out["password_mode"] == "secret"
    assert all(m["key"] != "password" for m in out["methods"])


def test_hiding_the_form_never_locks_the_break_glass_account_out(client, db, seeded):
    """Le point le plus important du lot: c'est de la lisibilite, pas du controle.

    Si masquer le formulaire empechait la connexion locale, une organisation qui
    active le mode secret perdrait son compte de secours le jour ou l'IdP tombe,
    c'est a dire exactement le jour ou elle en a besoin.
    """
    _configure(client, password_mode="secret")
    client.cookies.clear()
    r = client.post("/api/auth/login", json={"email": "admin@test", "password": "pw"})
    assert r.status_code == 200, r.text


def test_renewing_the_secret_invalidates_the_previous_link(client, db, seeded):
    first = _configure(client, password_mode="secret")["password_secret"]
    second = _configure(client, password_secret="")["password_secret"]
    assert second and second != first
    assert _public(client, k=first)["password_mode"] == "secret"
    assert _public(client, k=second)["password_mode"] == "visible"


# ---- ce que la configuration garantit -------------------------------------------

def test_every_method_stays_listed_for_the_admin_screen(db, seeded):
    """L'ecran d'administration doit pouvoir rallumer ce qui est eteint."""
    set_auth_config(db, {"login_methods": [{"key": "oidc", "enabled": False}]})
    db.commit()
    cfg = get_auth_config(db)
    assert [m["key"] for m in cfg["login_methods"]] == ["oidc", "saml", "password"]


def test_the_default_screen_is_what_the_page_did_before(db, seeded):
    """Sans reglage, rien ne change pour une installation existante."""
    cfg = get_auth_config(db)
    screen = login_screen(cfg)
    assert screen["password_mode"] == "visible"
    assert [m["key"] for m in screen["methods"]] == ["password"]   # SSO non configure
