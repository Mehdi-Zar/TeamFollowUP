"""Le moral de l'equipe: trois niveaux, une date, et qui a le droit de le dire.

Trois niveaux et pas cinq: une echelle fine invite a la nuance, or ce qu'on lit
ici est un signal. La date compte autant que le niveau, parce qu'un moral de mars
affiche en septembre ment plus surement qu'une case vide.

Le point de droit est le plus important: c'est le moral de SON equipe, declare par
qui la mene, pas une note qu'un tiers lui attribue.
"""
from sqlalchemy import select

from app.models import Squad
from tests.conftest import login


def test_the_leader_declares_the_mood_of_their_own_squad(client, db, seeded):
    login(client, seeded["sl_a"])
    r = client.put(f"/api/squads/{seeded['squad_a']}/mood", json={"mood": "good"})
    assert r.status_code == 200, r.text
    assert r.json()["mood"] == "good"
    assert r.json()["mood_at"], "la date est posee par le serveur"

    detail = client.get(f"/api/squads/{seeded['squad_a']}").json()
    assert detail["mood"] == "good" and detail["mood_at"]


def test_a_stranger_does_not_rate_somebody_else_s_team(client, db, seeded):
    login(client, seeded["sl_b"])
    r = client.put(f"/api/squads/{seeded['squad_a']}/mood", json={"mood": "bad"})
    assert r.status_code == 403


def test_a_member_cannot_declare_it_either(client, db, seeded):
    login(client, seeded["member"])
    assert client.put(f"/api/squads/{seeded['squad_a']}/mood",
                      json={"mood": "good"}).status_code == 403


def test_only_the_three_levels_are_accepted(client, db, seeded):
    """Une echelle fermee: un quatrieme niveau arriverait par l'API et personne ne
    saurait l'afficher."""
    login(client, seeded["sl_a"])
    assert client.put(f"/api/squads/{seeded['squad_a']}/mood",
                      json={"mood": "excellent"}).status_code == 422
    for level in ("good", "mixed", "bad"):
        assert client.put(f"/api/squads/{seeded['squad_a']}/mood",
                          json={"mood": level}).status_code == 200


def test_clearing_the_mood_clears_its_date_too(client, db, seeded):
    """Sinon une date resterait a l'ecran sans rien dater."""
    login(client, seeded["sl_a"])
    client.put(f"/api/squads/{seeded['squad_a']}/mood", json={"mood": "mixed"})
    out = client.put(f"/api/squads/{seeded['squad_a']}/mood", json={"mood": None}).json()
    assert out["mood"] is None and out["mood_at"] is None


def test_the_comment_is_kept_and_bounded(client, db, seeded):
    login(client, seeded["sl_a"])
    out = client.put(f"/api/squads/{seeded['squad_a']}/mood",
                     json={"mood": "bad", "comment": "Deux departs et une astreinte"}).json()
    assert out["mood_comment"] == "Deux departs et une astreinte"
    long = client.put(f"/api/squads/{seeded['squad_a']}/mood",
                      json={"mood": "bad", "comment": "x" * 500}).json()
    assert len(long["mood_comment"]) == 300


def test_the_dashboard_card_carries_the_mood(client, db, seeded):
    """C'est la seule donnee de cette grille qu'aucun calcul ne produit."""
    login(client, seeded["sl_a"])
    client.put(f"/api/squads/{seeded['squad_a']}/mood", json={"mood": "good"})

    login(client, seeded["tribe"])
    cards = {c["squad_id"]: c for c in client.get("/api/dashboard").json()["cards"]}
    assert cards[seeded["squad_a"]]["mood"] == "good"
    assert cards[seeded["squad_a"]]["mood_at"]
    assert cards[seeded["squad_b"]]["mood"] is None


def test_the_tribe_leader_may_declare_it_for_a_squad_of_their_tribe(client, db, seeded):
    """Meme regle que le reste de l'edition d'une squad, pas une regle de plus."""
    login(client, seeded["tribe"])
    assert client.put(f"/api/squads/{seeded['squad_a']}/mood",
                      json={"mood": "mixed"}).status_code == 200
    login(client, seeded["tribe2"])
    assert client.put(f"/api/squads/{seeded['squad_a']}/mood",
                      json={"mood": "bad"}).status_code == 403


def test_a_co_leader_declares_it_too(client, db, seeded):
    """Les co-responsables ont les memes droits sur leur squad."""
    sl_b = db.scalar(select(Squad).where(Squad.id == seeded["squad_b"])).leader_user_id
    login(client, seeded["tribe"])
    client.put(f"/api/squads/{seeded['squad_a']}", json={"co_leader_user_ids": [sl_b]})

    login(client, seeded["sl_b"])
    assert client.put(f"/api/squads/{seeded['squad_a']}/mood",
                      json={"mood": "good"}).status_code == 200


# ----- le nuage, dans les documents ----------------------------------------------

def test_the_html_export_draws_a_cloud_and_no_emoji(client, db, seeded):
    """Un emoji depend de la police du poste qui ouvre le document: il sort en
    carre la ou elle manque. Le nuage est dessine, donc il sort partout pareil."""
    from app import report as report_mod
    from app.models import User

    login(client, seeded["sl_a"])
    client.put(f"/api/squads/{seeded['squad_a']}/mood", json={"mood": "good"})

    viewer = db.scalar(select(User).where(User.email == seeded["admin"]))
    data = report_mod.build_report_data(db, None, 2026, 7, lang="fr", viewer=viewer,
                                        squad_id=seeded["squad_a"])
    html = report_mod.render_html(data)

    assert 'class="mood-cloud"' in html, "le nuage est dessine dans le document"
    assert "\U0001F600" not in html and "\U0001F610" not in html and "\U0001F641" not in html


def test_an_undeclared_mood_draws_nothing(client, db, seeded):
    """Un nuage gris se lirait comme un quatrieme niveau, alors que
    « non renseigne » n'en est pas un."""
    from app.reportcommon import mood_cloud_svg

    assert mood_cloud_svg(None) == ""
    assert mood_cloud_svg("good").startswith("<svg")
    # La bouche redit le niveau, pour qui imprime en noir et blanc.
    assert mood_cloud_svg("good") != mood_cloud_svg("bad")


def test_the_deck_draws_the_cloud_as_shapes(client, db, seeded):
    """Sur une slide, le nuage est un assemblage de formes: nuage, deux yeux, une
    bouche. C'est ce qui lui permet de sortir sans aucune police."""
    import io as _io

    import pytest

    pptx = pytest.importorskip("pptx")
    from app import report as report_mod
    from app.models import User

    login(client, seeded["sl_a"])
    client.put(f"/api/squads/{seeded['squad_a']}/mood", json={"mood": "bad"})

    viewer = db.scalar(select(User).where(User.email == seeded["admin"]))
    blob = report_mod.render_pptx(report_mod.build_report_data(
        db, None, 2026, 7, lang="fr", viewer=viewer, squad_id=seeded["squad_a"]))
    prs = pptx.Presentation(_io.BytesIO(blob))
    # La geometrie d'une forme automatique se lit dans auto_shape_type; shape_type
    # dit seulement "forme automatique" et ne distingue donc pas un nuage d'un carre.
    kinds = []
    for sh in prs.slides[0].shapes:
        try:
            kinds.append(str(sh.auto_shape_type))
        except (ValueError, AttributeError, TypeError):
            continue

    assert any(k.startswith("CLOUD") for k in kinds), "le nuage lui-meme"
    assert sum(1 for k in kinds if k.startswith("OVAL")) >= 2, "les deux yeux"
