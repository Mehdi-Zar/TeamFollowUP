"""Revenir sur un acces: le revoquer, puis le rendre.

L'ecran ne montrait que la file d'attente et le serveur refusait de valider tout
ce qui n'etait pas « en attente ». Une fois la decision prise elle etait donc
definitive dans les deux sens: un acces accorde ne se reprenait pas, un acces
repris ne se rendait pas. Un droit d'acces qui ne se defait pas n'est pas un
droit, c'est une propriete.

Deux garde-fous comptent autant que la fonction elle-meme: on ne se revoque pas
soi-meme, et on ne revoque pas le dernier administrateur actif. Sans eux, un
clic de trop oblige a ressortir le compte de secours pour une operation
ordinaire.
"""
from sqlalchemy import select

from app.models import User
from tests.conftest import login


def _account(client, email):
    rows = client.get("/api/access-requests/accounts").json()["accounts"]
    return next((a for a in rows if a["email"] == email), None)


def test_a_granted_access_can_be_taken_back(client, db, seeded):
    login(client, seeded["admin"])
    r = client.post(f"/api/access-requests/{seeded['member_id']}/deny", json={})
    assert r.status_code == 200, r.text
    assert db.get(User, seeded["member_id"]).status == "disabled"


def test_a_revoked_access_can_be_given_back(client, db, seeded):
    """C'est la meme decision qu'une validation: un role, une tribu, une squad."""
    login(client, seeded["admin"])
    client.post(f"/api/access-requests/{seeded['member_id']}/deny", json={})

    r = client.post(f"/api/access-requests/{seeded['member_id']}/approve",
                    json={"role": "member", "tribe_id": seeded["t1"], "squad_id": None})
    assert r.status_code == 200, r.text
    back = db.get(User, seeded["member_id"])
    assert back.status == "active" and back.role == "member"


def test_reinstating_says_so_in_the_trail(client, db, seeded):
    """« Valide » et « retabli » ne racontent pas la meme histoire."""
    from app.models import AuditLog

    login(client, seeded["admin"])
    client.post(f"/api/access-requests/{seeded['member_id']}/deny", json={})
    client.post(f"/api/access-requests/{seeded['member_id']}/approve",
                json={"role": "member", "tribe_id": seeded["t1"], "squad_id": None})

    row = db.scalars(select(AuditLog).where(AuditLog.action == "access.approve")
                     .order_by(AuditLog.id.desc())).first()
    assert row.detail.get("from") == "disabled"


def test_an_active_account_is_not_approved_twice(client, db, seeded):
    login(client, seeded["admin"])
    r = client.post(f"/api/access-requests/{seeded['member_id']}/approve",
                    json={"role": "member", "tribe_id": seeded["t1"], "squad_id": None})
    assert r.status_code == 409


def _second_admin(db, email="admin2@test"):
    """Un administrateur ordinaire: le compte seme est celui de secours, qui suit
    des regles a lui."""
    from app.security import hash_password
    u = User(email=email, display_name="Admin 2", role="admin", status="active",
             password_hash=hash_password("pw"))
    db.add(u)
    db.commit()
    return u


def test_nobody_revokes_their_own_access(client, db, seeded):
    """Un clic de trop ne doit pas fermer la porte sur celui qui appuie."""
    me = _second_admin(db)
    login(client, me.email)
    assert client.post(f"/api/access-requests/{me.id}/deny", json={}).status_code == 400


def test_an_administrator_can_be_revoked_while_another_remains(client, db, seeded):
    """Un compte compromis doit pouvoir partir, compte de secours ou pas."""
    other = _second_admin(db)
    login(client, seeded["admin"])
    assert client.post(f"/api/access-requests/{other.id}/deny", json={}).status_code == 200


def test_the_last_active_administrator_stays(client, db, seeded):
    """Sans administrateur actif, la moindre operation devient impossible.

    La regle se verifie ici sur elle-meme plutot que par la route: pour l'atteindre
    par l'API il faudrait un second administrateur pour appuyer, ce qui defait
    justement la condition qu'on veut eprouver."""
    from app.access import _would_leave_no_gatekeeper

    other = _second_admin(db)
    bg = db.scalar(select(User).where(User.is_break_glass.is_(True)))
    assert _would_leave_no_gatekeeper(db, other) is False, "le compte de secours en est un"

    bg.status = "disabled"
    db.commit()
    assert _would_leave_no_gatekeeper(db, other) is True, "il serait alors le dernier"


def test_a_tribe_leader_does_not_revoke_an_administrator(client, db, seeded):
    """L'ecran ne le proposait pas, l'API l'acceptait."""
    other = _second_admin(db)
    login(client, seeded["tribe"])
    assert client.post(f"/api/access-requests/{other.id}/deny", json={}).status_code == 403


def test_a_tribe_leader_does_not_revoke_another_tribe(client, db, seeded):
    login(client, seeded["tribe"])
    tribe2_id = db.scalar(select(User.id).where(User.email == seeded["tribe2"]))
    assert client.post(f"/api/access-requests/{tribe2_id}/deny", json={}).status_code == 403


def test_the_break_glass_account_is_never_listed_nor_revoked(client, db, seeded):
    """C'est la porte qui reste ouverte quand les autres se referment."""
    login(client, seeded["admin"])
    bg = db.scalar(select(User).where(User.is_break_glass.is_(True)))
    assert _account(client, bg.email) is None
    assert client.post(f"/api/access-requests/{bg.id}/deny", json={}).status_code == 403


def test_the_list_answers_who_has_access(client, db, seeded):
    login(client, seeded["admin"])
    rows = client.get("/api/access-requests/accounts").json()["accounts"]
    by_mail = {a["email"]: a for a in rows}
    assert by_mail[seeded["member"]]["status"] == "active"
    assert by_mail[seeded["sl_a"]]["role"] == "squad_leader"
    # Le compte de secours n'est pas dans la liste: on se regarde donc depuis un
    # compte ordinaire.
    login(client, seeded["tribe"])
    mine = {a["email"]: a for a in client.get("/api/access-requests/accounts").json()["accounts"]}
    assert mine[seeded["tribe"]]["is_self"] is True


def test_a_tribe_leader_only_sees_their_own_tribe(client, db, seeded):
    login(client, seeded["tribe"])
    mails = {a["email"] for a in client.get("/api/access-requests/accounts").json()["accounts"]}
    assert seeded["member"] in mails
    assert seeded["tribe2"] not in mails


def test_a_squad_leader_gets_no_list_because_they_do_not_revoke(client, db, seeded):
    """Montrer une liste sur laquelle on ne peut rien faire est une fausse promesse."""
    login(client, seeded["sl_a"])
    assert client.get("/api/access-requests/accounts").json()["accounts"] == []


def test_a_pending_account_stays_in_the_queue_not_in_the_list(client, db, seeded):
    """Les deux ecrans repondent a deux questions: ce qui reste a faire, et qui a
    acces. Un compte ne doit pas etre dans les deux."""
    pend = User(email="new@test", display_name="Nouveau", role="member", status="pending")
    db.add(pend)
    db.commit()

    login(client, seeded["admin"])
    assert _account(client, "new@test") is None
    queue = client.get("/api/access-requests").json()["requests"]
    assert any(r["email"] == "new@test" for r in queue)
