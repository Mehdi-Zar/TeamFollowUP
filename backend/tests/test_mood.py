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
