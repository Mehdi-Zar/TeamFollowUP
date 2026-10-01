"""Corporate directory search: Entra ID (Graph), Google Workspace, LDAP, merged.

The HTTP sources are answered by an httpx.MockTransport, LDAP by an ldap3
MOCK_SYNC connection: no network, but the real request building and parsing.
"""
import json
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

from app import directory
from app.directoryconfig import get_directory, set_directory
from tests.conftest import login


@pytest.fixture(autouse=True)
def _reset():
    directory._token_cache.clear()
    yield
    directory._transport = None
    directory._ldap_connection_factory = None
    directory._token_cache.clear()


def _graph_and_google(seen: list):
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        url = str(request.url)
        if "login.microsoftonline.com" in url:
            body = parse_qs(request.content.decode())
            assert body["grant_type"] == ["client_credentials"]
            assert body["scope"] == ["https://graph.microsoft.com/.default"]
            return httpx.Response(200, json={"access_token": "graph-token", "expires_in": 3600})
        if url.startswith("https://graph.microsoft.com/v1.0/users"):
            assert request.headers["ConsistencyLevel"] == "eventual"
            assert request.headers["Authorization"] == "Bearer graph-token"
            return httpx.Response(200, json={"value": [
                {"displayName": "Alice Martin", "givenName": "Alice", "surname": "Martin",
                 "mail": "Alice.Martin@corp.example", "jobTitle": None, "department": "Cloud"},
                {"displayName": "Sans mail", "userPrincipalName": "x_ext#EXT#@corp.onmicrosoft.com"},
            ]})
        if url.startswith("https://oauth2.googleapis.com/token"):
            return httpx.Response(200, json={"access_token": "google-token", "expires_in": 3600})
        if url.startswith("https://admin.googleapis.com/admin/directory/v1/users"):
            return httpx.Response(200, json={"users": [
                {"primaryEmail": "bob@corp.example", "name": {"fullName": "Bob Durand", "givenName": "Bob",
                                                              "familyName": "Durand"},
                 "organizations": [{"title": "DevOps", "department": "Infra"}]},
                {"primaryEmail": "gone@corp.example", "suspended": True, "name": {"fullName": "Gone"}},
            ]})
        return httpx.Response(404)
    return handler


def _google_key() -> str:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    k = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = k.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                          serialization.NoEncryption()).decode()
    return json.dumps({"client_email": "svc@proj.iam.gserviceaccount.com", "private_key": pem,
                       "token_uri": "https://oauth2.googleapis.com/token"})


def _ldap_factory(entries):
    from ldap3 import MOCK_SYNC, Connection, Server

    def factory(cfg):
        conn = Connection(Server("fake"), user="cn=svc,dc=corp", password="pw", client_strategy=MOCK_SYNC)
        conn.strategy.add_entry("cn=svc,dc=corp", {"userPassword": "pw", "objectClass": "person"})
        for dn, attrs in entries:
            conn.strategy.add_entry(dn, attrs)
        return conn
    return factory


def _configure(db, **kw):
    set_directory(db, kw)
    db.commit()


def test_entra_google_and_ldap_merged_by_email(db, seeded, client):
    seen = []
    directory._transport = httpx.MockTransport(_graph_and_google(seen))
    directory._ldap_connection_factory = _ldap_factory([
        ("cn=Alice Martin,ou=people,dc=corp", {"objectClass": "person", "displayName": "Alice Martin",
                                               "mail": "alice.martin@corp.example", "title": "Architecte",
                                               "givenName": "Alice", "sn": "Martin"}),
        ("cn=Carla,ou=people,dc=corp", {"objectClass": "person", "displayName": "Carla Ruiz",
                                        "mail": "carla@corp.example"}),
    ])
    _configure(db, entra_enabled=True, entra_tenant_id="t", entra_client_id="c", entra_client_secret="s",
               google_enabled=True, google_service_account_json=_google_key(),
               google_admin_subject="admin@corp.example",
               ldap_enabled=True, ldap_base_dn="dc=corp", ldap_bind_dn="cn=svc,dc=corp", ldap_bind_password="pw")

    login(client, seeded["sl_a"])
    r = client.get("/api/directory/search", params={"q": "a"})
    assert r.status_code == 422          # two characters at least
    r = client.get("/api/directory/search", params={"q": "ar"})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["sources"]["entra"]["ok"] and out["sources"]["google"]["ok"] and out["sources"]["ldap"]["ok"]
    by_email = {p["email"]: p for p in out["results"]}
    # Entra named Alice first, LDAP filled the title Entra did not have.
    alice = by_email["alice.martin@corp.example"]
    assert alice["source"] == "entra" and alice["title"] == "Architecte" and alice["department"] == "Cloud"
    assert by_email["bob@corp.example"]["title"] == "DevOps"
    assert "carla@corp.example" in by_email
    assert "gone@corp.example" not in by_email        # suspended in Google
    assert all("#ext#" not in e for e in by_email)    # no email: dropped
    # The Graph query searches the three name fields, accounts enabled only.
    graph = next(x for x in seen if "graph.microsoft.com/v1.0/users" in str(x.url))
    qs = parse_qs(urlsplit(str(graph.url)).query)
    assert qs["$filter"] == ["accountEnabled eq true"]
    assert '"displayName:ar"' in qs["$search"][0] and '"mail:ar"' in qs["$search"][0]


def test_a_failing_source_does_not_hide_the_others(db, seeded, client):
    def handler(request):
        if "login.microsoftonline.com" in str(request.url):
            return httpx.Response(401, json={"error": "invalid_client", "error_description": "bad secret"})
        return httpx.Response(404)
    directory._transport = httpx.MockTransport(handler)
    directory._ldap_connection_factory = _ldap_factory([
        ("cn=Dan,dc=corp", {"objectClass": "person", "displayName": "Dan Ray", "mail": "dan@corp.example"})])
    _configure(db, entra_enabled=True, entra_tenant_id="t", entra_client_id="c", entra_client_secret="x",
               ldap_enabled=True, ldap_base_dn="dc=corp")
    login(client, seeded["sl_a"])
    out = client.get("/api/directory/search", params={"q": "dan"}).json()
    assert out["sources"]["entra"]["ok"] is False and "bad secret" in out["sources"]["entra"]["error"]
    assert [p["email"] for p in out["results"]] == ["dan@corp.example"]


def test_ldap_filter_input_is_escaped(db):
    calls = []

    def factory(cfg):
        conn = _ldap_factory([])(cfg)
        orig = conn.search

        def spy(base, flt, *a, **kw):
            calls.append(flt)
            return orig(base, flt, *a, **kw)
        conn.search = spy
        return conn
    directory._ldap_connection_factory = factory
    cfg = get_directory(db)
    cfg.update(ldap_base_dn="dc=corp", ldap_search_attrs="cn,mail")
    directory.search_ldap(cfg, "a*)(uid=*")
    assert calls and "a\\2a\\29\\28uid=\\2a" in calls[0]


def test_search_rights_and_existing_accounts(db, seeded, client):
    login(client, seeded["sl_a"])
    assert client.get("/api/directory/status").json() == {"enabled": False, "sources": []}
    assert client.get("/api/directory/search", params={"q": "ab"}).status_code == 409
    directory._ldap_connection_factory = _ldap_factory([
        ("cn=M,dc=corp", {"objectClass": "person", "displayName": "Member", "mail": "member@test"})])
    _configure(db, ldap_enabled=True, ldap_base_dn="dc=corp")
    out = client.get("/api/directory/search", params={"q": "mem"}).json()
    assert out["results"][0]["user_id"] == seeded["member_id"]   # an account exists already
    login(client, seeded["member"])                              # a plain member does not search
    assert client.get("/api/directory/search", params={"q": "mem"}).status_code == 403


def test_admin_config_masks_secrets_and_tests_a_source(db, seeded, client):
    login(client, seeded["admin"])
    r = client.put("/api/admin/directory-config", json={"entra_enabled": True, "entra_client_secret": "s3cret",
                                                        "ldap_bind_password": "pw"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["entra_client_secret"] == "********" and body["ldap_bind_password"] == "********"
    assert "scim_token_hash" not in body and body["scim_base_url"].endswith("/scim/v2")
    # A mask sent back keeps the stored secret.
    client.put("/api/admin/directory-config", json={"entra_client_secret": "********"})
    assert get_directory(db)["entra_client_secret"] == "s3cret"
    # Admin is never a provisioning persona.
    assert client.put("/api/admin/directory-config", json={"scim_default_role": "admin"}).status_code == 400
    # The test button reports the source's own error.
    directory._transport = httpx.MockTransport(lambda req: httpx.Response(500))
    r = client.post("/api/admin/directory-config/test", json={"source": "entra", "q": "al",
                                                              "config": {"entra_tenant_id": "t",
                                                                         "entra_client_id": "c"}})
    assert r.json()["ok"] is False and "HTTP 500" in r.json()["error"]
    # A tribe leader cannot open the tab, even if it were ticked for the persona.
    login(client, seeded["tribe"])
    assert client.get("/api/admin/directory-config").status_code == 403
