"""People are shown by name everywhere, never by address.

When the identity provider or the directory sent no name, the email was stored
as the account's name, and the same screen showed some people by name and
others by address."""
from app.memberlink import looks_unnamed, person_name
from app.models import User
from tests.test_scim import _token


def test_person_name_prefers_a_real_name_and_never_keeps_an_address():
    assert person_name("jean.dupont@corp.example", "Jean Dupont") == "Jean Dupont"
    assert person_name("jean.dupont@corp.example", None, "  ") == "Jean Dupont"
    # A login sent in the name claim is no name.
    assert person_name("jean.dupont@corp.example", "jean.dupont@corp.example") == "Jean Dupont"
    assert person_name("jean.dupont@corp.example", "", "Jean  Dupont") == "Jean Dupont"
    assert looks_unnamed("a@b.c") and looks_unnamed("") and not looks_unnamed("Jean Dupont")


def test_a_scim_account_without_a_name_gets_one_from_its_email(db, seeded, client):
    auth = _token(client, seeded)
    r = client.post("/scim/v2/Users", headers=auth, json={"userName": "marie.curie@corp.example"})
    assert r.status_code == 201, r.text
    assert db.get(User, int(r.json()["id"])).display_name == "Marie Curie"
    # The directory sends the real name later: it replaces the one read from the email.
    uid = r.json()["id"]
    r = client.put(f"/scim/v2/Users/{uid}", headers=auth, json={
        "userName": "marie.curie@corp.example", "name": {"givenName": "Marie", "familyName": "Sklodowska"}})
    assert r.status_code == 200, r.text
    db.expire_all()
    assert db.get(User, int(uid)).display_name == "Marie Sklodowska"
