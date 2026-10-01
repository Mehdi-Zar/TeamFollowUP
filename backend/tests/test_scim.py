"""SCIM 2.0 provisioning, as Entra ID and Okta call it."""
from sqlalchemy import select

from app.models import Member, User
from tests.conftest import login

H = {"Content-Type": "application/scim+json"}


def _token(client, seeded, **cfg) -> dict:
    login(client, seeded["admin"])
    r = client.put("/api/admin/directory-config", json={"scim_enabled": True, **cfg})
    assert r.status_code == 200, r.text
    tok = client.post("/api/admin/directory-config/scim-token").json()["token"]
    client.cookies.clear()   # SCIM is a server calling: no session
    return {**H, "Authorization": f"Bearer {tok}"}


def test_token_required_and_hash_only(db, seeded, client):
    auth = _token(client, seeded)
    assert client.get("/scim/v2/Users").status_code == 401
    r = client.get("/scim/v2/Users", headers={"Authorization": "Bearer wrong"})
    assert r.status_code == 401 and r.headers["content-type"].startswith("application/scim+json")
    assert client.get("/scim/v2/ServiceProviderConfig", headers=auth).json()["patch"]["supported"] is True
    login(client, seeded["admin"])
    cfg = client.get("/api/admin/directory-config").json()
    assert cfg["scim_token_set"] is True and "scim_token_hash" not in cfg
    # A new token revokes the previous one.
    client.post("/api/admin/directory-config/scim-token")
    client.cookies.clear()
    assert client.get("/scim/v2/Users", headers=auth).status_code == 401


def test_entra_flow_create_find_patch_deactivate(db, seeded, client):
    auth = _token(client, seeded, scim_default_tribe_id=seeded["t1"], scim_default_role="squad_leader")
    # A team member typed before the account existed is linked when it is created.
    db.add(Member(squad_id=seeded["squad_a"], full_name="Eve Adams", email="eve@corp.example"))
    db.commit()
    # Entra looks the person up first.
    r = client.get('/scim/v2/Users?filter=userName eq "eve@corp.example"', headers=auth)
    assert r.json()["totalResults"] == 0
    r = client.post("/scim/v2/Users", headers=auth, json={
        "schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"], "externalId": "obj-123",
        "userName": "Eve@corp.example", "active": True, "displayName": "Eve Adams",
        "emails": [{"primary": True, "type": "work", "value": "eve@corp.example"}],
        "name": {"givenName": "Eve", "familyName": "Adams"}})
    assert r.status_code == 201, r.text
    uid = r.json()["id"]
    u = db.get(User, int(uid))
    assert (u.email, u.role, u.tribe_id, u.status) == ("eve@corp.example", "squad_leader", seeded["t1"], "active")
    db.expire_all()
    assert db.scalars(select(Member).where(Member.email == "eve@corp.example")).one().user_id == int(uid)
    # A second create is a conflict, as both connectors expect.
    assert client.post("/scim/v2/Users", headers=auth, json={"userName": "eve@corp.example"}).status_code == 409
    # Found again by externalId and by email.
    assert client.get('/scim/v2/Users?filter=externalId eq "obj-123"', headers=auth).json()["totalResults"] == 1
    assert client.get('/scim/v2/Users?filter=emails[type eq "work"].value eq "eve@corp.example"',
                      headers=auth).json()["totalResults"] == 1
    # Entra's PATCH: capitalised op, string boolean, path given.
    r = client.patch(f"/scim/v2/Users/{uid}", headers=auth, json={
        "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
        "Operations": [{"op": "Replace", "path": "displayName", "value": "Eve Adams-Lee"},
                       {"op": "Replace", "path": "active", "value": "False"},
                       {"op": "Add", "path": "urn:ietf:params:scim:schemas:extension:enterprise:2.0:User:department",
                        "value": "Cloud"}]})
    assert r.status_code == 200, r.text
    assert r.json()["active"] is False and r.json()["displayName"] == "Eve Adams-Lee"
    db.expire_all()
    assert db.get(User, int(uid)).status == "disabled"
    assert db.get(User, int(uid)).role == "squad_leader"   # never touched by SCIM


def test_okta_patch_without_path_and_delete_deactivates(db, seeded, client):
    auth = _token(client, seeded)
    uid = client.post("/scim/v2/Users", headers=auth,
                      json={"userName": "frank@corp.example", "name": {"givenName": "Frank", "familyName": "Lo"}}
                      ).json()["id"]
    r = client.patch(f"/scim/v2/Users/{uid}", headers=auth,
                     json={"Operations": [{"op": "replace", "value": {"active": False}}]})
    assert r.json()["active"] is False
    r = client.put(f"/scim/v2/Users/{uid}", headers=auth,
                   json={"userName": "frank@corp.example", "active": True, "displayName": "Frank Lo"})
    assert r.json()["active"] is True
    assert client.delete(f"/scim/v2/Users/{uid}", headers=auth).status_code == 204
    db.expire_all()
    u = db.get(User, int(uid))
    assert u is not None and u.status == "disabled"   # history kept


def test_break_glass_invisible_groups_read_only_and_paging(db, seeded, client):
    auth = _token(client, seeded)
    users = client.get("/scim/v2/Users?startIndex=1&count=2", headers=auth).json()
    assert users["itemsPerPage"] == 2 and users["totalResults"] == 5   # 6 accounts minus break-glass
    admin_id = db.scalars(select(User.id).where(User.email == "admin@test")).one()
    assert client.get(f"/scim/v2/Users/{admin_id}", headers=auth).status_code == 404
    groups = client.get("/scim/v2/Groups", headers=auth).json()
    assert {g["displayName"] for g in groups["Resources"]} == {"Tribe One", "Tribe Two"}
    r = client.post("/scim/v2/Groups", headers=auth, json={"displayName": "x"})
    assert r.status_code == 403 and r.json()["scimType"] == "mutability"
    assert client.get('/scim/v2/Users?filter=title co "x"', headers=auth).status_code == 400
