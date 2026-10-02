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


def _steps(out):
    return {s["key"]: s for s in out["steps"]}


def test_active_directory_is_its_own_source_with_its_own_settings(db, seeded, client):
    """AD and another LDAP do not share settings: both can be on at once."""
    directory._ldap_connection_factory = _ldap_factory([
        ("cn=Eva,dc=corp", {"objectClass": "user", "objectCategory": "person", "displayName": "Eva Roy",
                             "mail": "eva@corp.example", "userAccountControl": "512"})])
    _configure(db, ad_enabled=True, ad_base_dn="dc=corp", ldap_base_dn="")
    cfg = get_directory(db)
    assert "userAccountControl" in cfg["ad_user_filter"] and "sAMAccountName" in cfg["ad_search_attrs"]
    assert "sAMAccountName" not in cfg["ldap_search_attrs"]
    login(client, seeded["sl_a"])
    out = client.get("/api/directory/search", params={"q": "eva"}).json()
    assert out["sources"]["ad"]["ok"] and [p["source"] for p in out["results"]] == ["ad"]
    assert "ldap" not in out["sources"]


def test_the_ldap_test_walks_every_step_and_shows_the_raw_entry(db, seeded, client):
    directory._ldap_connection_factory = _ldap_factory([
        ("dc=corp", {"objectClass": "domain", "dc": "corp"}),
        ("cn=Fay,dc=corp", {"objectClass": "person", "displayName": "Fay Lin", "mail": "fay@corp.example",
                            "sn": "Lin"}),
        ("cn=NoMail,dc=corp", {"objectClass": "person", "displayName": "No Mail Fay"}),
    ])
    login(client, seeded["admin"])
    r = client.post("/api/admin/directory-config/test", json={
        "source": "ldap", "q": "fay",
        "config": {"ldap_base_dn": "dc=corp", "ldap_bind_dn": "cn=svc,dc=corp", "ldap_bind_password": "pw",
                   "ldap_user_filter": "(objectClass=person)"}})
    out = r.json()
    assert out["ok"] and out["count"] == 1, out
    st = _steps(out)
    assert [s["key"] for s in out["steps"]] == ["config", "connect", "bind", "base", "query", "attributes"]
    assert st["bind"]["status"] == "ok" and "cn=svc,dc=corp" in st["bind"]["detail"]
    # One entry has no email: said, not silently dropped.
    assert st["query"]["status"] == "warn" and "sans email" in st["query"]["detail"]
    # givenName is mapped but the entry does not carry it: the mapping is flagged.
    assert st["attributes"]["status"] == "warn" and "givenName" in st["attributes"]["detail"]
    assert out["raw"]["attributes"]["mail"] == "fay@corp.example"


def test_ad_bind_sub_codes_are_translated():
    class Conn:
        result = {"description": "invalidCredentials",
                  "message": "80090308: LdapErr: DSID-0C09044E, comment: AcceptSecurityContext error, data 775, v4563"}
    assert "verrouillé" in str(directory._bind_error(Conn(), "Active Directory"))


def test_a_missing_base_fails_at_the_base_step(db, seeded, client):
    directory._ldap_connection_factory = _ldap_factory([])
    login(client, seeded["admin"])
    out = client.post("/api/admin/directory-config/test", json={
        "source": "ldap", "q": "x", "config": {"ldap_base_dn": "ou=nowhere,dc=corp",
                                                "ldap_bind_dn": "cn=svc,dc=corp", "ldap_bind_password": "pw"}}).json()
    assert out["ok"] is False and out["steps"][-1]["key"] == "base" and out["steps"][-1]["status"] == "fail"


def test_the_entra_test_reads_the_permissions_the_token_carries(db, seeded, client):
    import jwt as pyjwt
    tok = pyjwt.encode({"roles": ["Group.Read.All"]}, "k" * 32, algorithm="HS256")

    def handler(request):
        if "login.microsoftonline.com" in str(request.url):
            return httpx.Response(200, json={"access_token": tok, "expires_in": 3600})
        return httpx.Response(403, json={"error": {"message": "Insufficient privileges"}})
    directory._transport = httpx.MockTransport(handler)
    login(client, seeded["admin"])
    out = client.post("/api/admin/directory-config/test", json={
        "source": "entra", "q": "al",
        "config": {"entra_tenant_id": "t", "entra_client_id": "c", "entra_client_secret": "s"}}).json()
    st = _steps(out)
    assert st["config"]["status"] == "ok"
    assert st["token"]["status"] == "warn" and "User.Read.All" in st["token"]["detail"]
    assert st["query"]["status"] == "fail" and "403" in st["query"]["detail"] and out["ok"] is False


def test_the_scim_test_checks_the_token_and_lists_refused_calls(db, seeded, client):
    from app.routers import scim
    scim.RECENT.clear()
    login(client, seeded["admin"])
    client.put("/api/admin/directory-config", json={"scim_enabled": True})
    tok = client.post("/api/admin/directory-config/scim-token").json()["token"]
    client.cookies.clear()
    assert client.get("/scim/v2/Users", headers={"Authorization": "Bearer nope"}).status_code == 401
    login(client, seeded["admin"])
    out = client.post("/api/admin/directory-config/scim-test", json={"token": "nope"}).json()
    st = _steps(out)
    assert st["enabled"]["status"] == "ok" and st["token"]["status"] == "fail" and out["ok"] is False
    assert out["calls"][0]["outcome"] == "refused_bad_token" and st["calls"]["status"] == "warn"
    out = client.post("/api/admin/directory-config/scim-test", json={"token": tok}).json()
    assert _steps(out)["token"]["status"] == "ok"


def test_a_group_search_in_ldap_and_ad(db, seeded, client):
    directory._ldap_connection_factory = _ldap_factory([
        ("dc=corp", {"objectClass": "domain"}),
        ("cn=cloud-ops,dc=corp", {"objectClass": "groupOfNames", "cn": "cloud-ops", "description": "Ops",
                                  "member": ["cn=a,dc=corp", "cn=b,dc=corp"]}),
        ("cn=CloudAdmins,dc=corp", {"objectClass": "group", "objectCategory": "group", "cn": "CloudAdmins",
                                    "mail": "cloudadmins@corp.example", "member": ["cn=a,dc=corp"]}),
    ])
    login(client, seeded["admin"])
    out = client.post("/api/admin/directory-config/test", json={
        "source": "ldap", "mode": "group", "q": "cloud",
        "config": {"ldap_base_dn": "dc=corp", "ldap_bind_dn": "cn=svc,dc=corp", "ldap_bind_password": "pw"}}).json()
    assert out["ok"] and out["mode"] == "group", out
    assert [g["name"] for g in out["groups"]] == ["cloud-ops"] and out["groups"][0]["members"] == 2
    out = client.post("/api/admin/directory-config/test", json={
        "source": "ad", "mode": "group", "q": "cloud",
        "config": {"ad_base_dn": "dc=corp", "ad_bind_dn": "cn=svc,dc=corp", "ad_bind_password": "pw"}}).json()
    assert out["ok"] and [g["email"] for g in out["groups"]] == ["cloudadmins@corp.example"]


def test_a_custom_ldap_query_returns_raw_entries(db, seeded, client):
    directory._ldap_connection_factory = _ldap_factory([
        ("dc=corp", {"objectClass": "domain"}),
        ("cn=Gus,dc=corp", {"objectClass": "person", "cn": "Gus", "mail": "gus@corp.example"}),
    ])
    login(client, seeded["admin"])
    out = client.post("/api/admin/directory-config/test", json={
        "source": "ldap", "mode": "custom",
        "custom": {"filter": "(mail=gus@*)", "attributes": "cn,mail", "scope": "sub", "limit": 5},
        "config": {"ldap_base_dn": "dc=corp", "ldap_bind_dn": "cn=svc,dc=corp", "ldap_bind_password": "pw"}}).json()
    assert out["ok"], out
    assert out["entries"][0]["dn"] == "cn=Gus,dc=corp" and out["entries"][0]["attributes"]["mail"] == "gus@corp.example"
    # A broken filter is a failed step that says why, not a 500.
    out = client.post("/api/admin/directory-config/test", json={
        "source": "ldap", "mode": "custom", "custom": {"filter": "(mail=gus"},
        "config": {"ldap_base_dn": "dc=corp", "ldap_bind_dn": "cn=svc,dc=corp", "ldap_bind_password": "pw"}}).json()
    assert out["ok"] is False and out["steps"][-1]["key"] == "query"


def test_entra_groups_and_a_custom_graph_path(db, seeded, client):
    import jwt as pyjwt
    tok = pyjwt.encode({"roles": ["User.Read.All"]}, "k" * 32, algorithm="HS256")
    seen = []

    def handler(request):
        seen.append(str(request.url))
        if "login.microsoftonline.com" in str(request.url):
            return httpx.Response(200, json={"access_token": tok, "expires_in": 3600})
        if "/v1.0/groups" in str(request.url):
            return httpx.Response(200, json={"value": [{"displayName": "Cloud Ops", "mail": "ops@corp.example",
                                                        "groupTypes": ["Unified"], "id": "g1"}]})
        return httpx.Response(200, json={"value": [{"id": "u1"}]})
    directory._transport = httpx.MockTransport(handler)
    cfg = {"entra_tenant_id": "t", "entra_client_id": "c", "entra_client_secret": "s"}
    login(client, seeded["admin"])
    out = client.post("/api/admin/directory-config/test", json={"source": "entra", "mode": "group", "q": "cloud",
                                                               "config": cfg}).json()
    st = {s["key"]: s for s in out["steps"]}
    # User.Read.All does not read groups: said before Graph answers 403.
    assert st["token"]["status"] == "warn" and "Group.Read.All" in st["token"]["detail"]
    assert out["groups"][0]["kind"] == "Microsoft 365"
    out = client.post("/api/admin/directory-config/test", json={"source": "entra", "mode": "custom",
                                                               "custom": {"path": "/v1.0/users?$top=1"},
                                                               "config": cfg}).json()
    assert out["ok"] and out["body"]["status"] == 200 and '"u1"' in out["body"]["text"]
    assert seen[-1].startswith("https://graph.microsoft.com/v1.0/users")
    # Never another host.
    for bad in ("https://evil.example/x", "//evil.example/x", "/v1.0/../../x", "/other/path"):
        out = client.post("/api/admin/directory-config/test", json={"source": "entra", "mode": "custom",
                                                                   "custom": {"path": bad}, "config": cfg}).json()
        assert out["ok"] is False, bad
    assert not any("evil" in u for u in seen)
