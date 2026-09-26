"""What the screen receives when a call fails: a sentence, in the asked language."""
from tests.conftest import login


def test_a_validation_error_names_the_field_in_french_by_default(client, seeded):
    login(client, seeded["admin"])
    r = client.post("/api/tribes", json={"name": "T", "display_order": "abc"})
    assert r.status_code == 422
    err = r.json()["detail"][0]
    assert err["msg"] == "display_order : nombre entier attendu"
    assert err["type"] == "int_parsing" and err["loc"][-1] == "display_order"


def test_a_validation_error_is_in_english_when_asked(client, seeded):
    login(client, seeded["admin"])
    r = client.post("/api/tribes", json={"display_order": 1}, headers={"Accept-Language": "en"})
    assert r.status_code == 422
    assert r.json()["detail"][0]["msg"] == "name: required field"


def test_a_reference_to_nothing_is_a_409_not_a_crash(client, seeded):
    login(client, seeded["admin"])
    r = client.post("/api/squads", json={"name": "Orpheline", "tribe_id": 999999})
    assert r.status_code in (404, 409), r.text
    assert "Internal" not in r.text


def test_the_email_export_refuses_a_word_for_a_number_of_days(client, seeded):
    login(client, seeded["admin"])
    r = client.post("/api/reports/weekly/email", json={"to": "a@b.c", "since_days": "abc"})
    assert r.status_code in (400, 403, 422), r.text
    assert "Internal" not in r.text


def test_a_leader_cannot_tag_a_squad_of_another_tribe_in_the_feed(client, seeded):
    login(client, seeded["sl_a"])
    r = client.post("/api/feed", json={"content": "Bonjour", "kind": "info", "squad_id": seeded["squad_c"]})
    assert r.status_code == 404
    assert client.post("/api/feed", json={"content": "Bonjour", "kind": "info",
                                           "squad_id": seeded["squad_a"]}).status_code == 201


def test_an_unknown_api_route_says_so_in_french(client):
    r = client.get("/api/does-not-exist")
    assert r.status_code == 404
    assert r.json()["detail"] == "Route inconnue"


def test_after_sso_only_a_path_of_the_app_is_followed():
    from app.routers.auth import _safe_next
    assert _safe_next("/squads/12?year=2026") == "/squads/12?year=2026"
    for bad in ("https://evil.example", "//evil.example", "/\evil.example", "/api/auth/logout", "/login", "", None):
        assert _safe_next(bad) == "/", bad
