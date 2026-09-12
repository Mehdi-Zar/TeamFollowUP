"""Personnalisation de l'apparence: ce qui sort d'ici part dans une feuille de style.

C'est ce qui rend ce module different d'un reglage ordinaire. Une couleur non
validee suffirait a casser l'application pour tout le monde
(``--navy: red; } body { display:none } /*``), et une image distante ferait
dependre l'affichage d'un serveur tiers, capable de compter qui ouvre l'ecran de
connexion et quand.

Les tests portent donc d'abord sur ce qui est refuse, puis sur le fait que ce qui
est accepte arrive vraiment jusqu'a la page.
"""
from app.branding import css_variables, defaults, get_branding, sanitize, set_branding
from tests.conftest import login

PNG = "data:image/png;base64,iVBORw0KGgo="


# ---- ce qui est refuse -----------------------------------------------------------

def test_a_colour_that_is_not_a_colour_is_refused():
    """Le cas qui compte: la valeur finit dans une feuille de style."""
    out = sanitize({"navy": "red; } body { display:none } /*"})
    assert out["navy"] == defaults()["navy"]
    assert sanitize({"accent": "javascript:alert(1)"})["accent"] == defaults()["accent"]
    assert sanitize({"bg": ""})["bg"] == defaults()["bg"]
    # Les deux ecritures legitimes passent.
    assert sanitize({"navy": "#abc"})["navy"] == "#abc"
    assert sanitize({"navy": "#A1B2C3"})["navy"] == "#A1B2C3"


def test_a_remote_image_is_refused_rather_than_stored():
    """L'affichage ne doit dependre d'aucun serveur tiers, et une capture de
    l'ecran de connexion ne doit pas fuiter vers un domaine qu'on ne controle pas."""
    out = sanitize({"logo": "https://tiers.example/logo.png", "favicon": PNG})
    assert out["logo"] == ""
    assert out["favicon"] == PNG


def test_a_font_outside_the_list_falls_back():
    """Le nom part tel quel dans font-family: la liste est fermee."""
    assert sanitize({"font": "'; } * { display:none } @font-face {"})["font"] == "system"
    assert sanitize({"font": "serif"})["font"] == "serif"


def test_numbers_are_clamped_not_rejected():
    """Un rayon de 400 pixels est une faute de frappe, pas une raison d'echouer."""
    assert sanitize({"radius": 400})["radius"] == 24
    assert sanitize({"radius": -5})["radius"] == 0
    assert sanitize({"font_scale": 999})["font_scale"] == 125
    assert sanitize({"radius": "abc"})["radius"] == defaults()["radius"]


def test_an_oversized_image_cannot_bloat_every_page_load(client, db, seeded):
    """Ce blob est lu a chaque chargement, par tout le monde, avant authentification."""
    huge = "data:image/png;base64," + ("A" * 500_000)
    assert len(sanitize({"logo": huge})["logo"]) <= 400_000


# ---- ce qui est accepte arrive jusqu'a la page -----------------------------------

def test_the_theme_reaches_the_public_config(client, db, seeded):
    login(client, "admin@test")
    r = client.put("/api/admin/branding", json={"navy": "#101010", "accent": "#ABCDEF",
                                                "radius": 4, "density": "compact", "logo": PNG})
    assert r.status_code == 200, r.text

    client.cookies.clear()
    public = client.get("/api/config").json()["branding"]
    assert public["css"]["--navy"] == "#101010"
    assert public["css"]["--accent"] == "#ABCDEF"
    assert public["css"]["--radius"] == "4px"
    assert public["density"] == "compact"
    assert public["logo"] == PNG


def test_the_public_config_carries_variables_not_raw_settings(client, db, seeded):
    """La page applique des variables CSS: le nom de chaque variable est decide au
    meme endroit que sa validation, pas cote client."""
    css = css_variables(defaults())
    assert css["--navy"].startswith("#")
    assert css["--font-family"].startswith("Calibri")
    assert css["--font-scale"] == "1.00"
    assert "--shadow" not in css                      # les ombres sont actives par defaut
    assert css_variables(sanitize({"shadows": False}))["--shadow"] == "none"


def test_only_an_admin_changes_the_look(client, db, seeded):
    login(client, seeded["tribe"])
    assert client.get("/api/admin/branding").status_code == 403
    assert client.put("/api/admin/branding", json={"navy": "#000000"}).status_code == 403


def test_reset_gives_back_the_shipped_theme(client, db, seeded):
    """La seule sortie sure d'une combinaison devenue illisible."""
    login(client, "admin@test")
    client.put("/api/admin/branding", json={"navy": "#000000", "bg": "#000000", "text": "#000000"})
    out = client.put("/api/admin/branding", json={"reset": True}).json()
    assert out == defaults()
    assert get_branding(db)["navy"] == defaults()["navy"]


def test_a_corrupt_stored_theme_falls_back_instead_of_breaking_the_page(db, seeded):
    from app.models import AppSetting

    db.add(AppSetting(key="branding", value="{ pas du json"))
    db.commit()
    assert get_branding(db) == defaults()


# ---- le pied de page des emails --------------------------------------------------

def test_the_email_footer_travels_with_the_smtp_config(client, db, seeded):
    """Un reglage que personne ne transporte est un reglage decoratif."""
    from app.smtpconfig import get_smtp

    login(client, "admin@test")
    client.put("/api/admin/branding", json={"email_footer": "Message automatique"})
    assert get_smtp(db)["email_footer"] == "Message automatique"


def test_the_footer_is_appended_to_what_is_sent():
    """Teste sans base: mail.py recoit la configuration, il ne la lit pas."""
    import smtplib
    from unittest.mock import patch

    from app.mail import send_email

    sent = {}

    class FakeSMTP:
        def __init__(self, *a, **k): pass
        def starttls(self, **k): pass
        def login(self, *a): pass
        def send_message(self, msg): sent["msg"] = msg
        def quit(self): pass

    cfg = {"enabled": True, "host": "relay", "port": 25, "from_addr": "a@b",
           "email_footer": "Ne pas repondre"}
    with patch.object(smtplib, "SMTP", FakeSMTP):
        assert send_email(cfg, "x@y", "sujet", "corps") is True
    assert "Ne pas repondre" in sent["msg"].get_content()


def test_the_footer_cannot_inject_markup_into_an_html_email():
    """Il est saisi dans un champ libre et rendu dans du HTML."""
    import smtplib
    from unittest.mock import patch

    from app.mail import send_email

    sent = {}

    class FakeSMTP:
        def __init__(self, *a, **k): pass
        def starttls(self, **k): pass
        def login(self, *a): pass
        def send_message(self, msg): sent["msg"] = msg
        def quit(self): pass

    cfg = {"enabled": True, "host": "relay", "port": 25, "from_addr": "a@b",
           "email_footer": "<script>alert(1)</script>"}
    with patch.object(smtplib, "SMTP", FakeSMTP):
        send_email(cfg, "x@y", "sujet", "<p>corps</p>", html=True)
    html = sent["msg"].get_payload()[1].get_content()
    assert "<script>" not in html and "&lt;script&gt;" in html
