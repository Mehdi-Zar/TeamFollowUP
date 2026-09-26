"""Prometheus metrics: exposition, protection, and the labels that matter.

The one thing worth guarding against here is cardinality. A metrics endpoint that
labels by raw path turns every squad id, every year and every export filename into
its own time series, and the failure shows up weeks later as a Prometheus that
falls over. The route-template test below is the guard for that.
"""
from app import metrics as metrics_mod
from app.config import settings
from tests.conftest import login


def _scrape(client) -> str:
    r = client.get("/metrics")
    assert r.status_code == 200, r.text
    return r.text


def test_metrics_endpoint_exposes_the_prometheus_format(client):
    r = client.get("/metrics")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/plain")
    body = r.text
    assert "# HELP teamfollowup_http_requests_total" in body
    assert "# TYPE teamfollowup_http_request_duration_seconds histogram" in body
    assert "teamfollowup_build_info" in body


def test_requests_are_counted_by_route_template_not_by_path(client, seeded):
    """/api/squads/1 and /api/squads/2 must share one series, not create two."""
    login(client, "admin@test")
    squads = client.get("/api/squads").json()
    assert len(squads) >= 2
    for s in squads[:2]:
        client.get(f"/api/squads/{s['id']}")

    body = _scrape(client)
    # The identifiers must appear nowhere in the metric labels.
    for s in squads[:2]:
        assert f'route="/api/squads/{s["id"]}"' not in body
    # ... and the template must be there instead, whatever FastAPI named the param.
    assert 'route="/api/squads/{' in body


def test_unknown_paths_collapse_into_one_series(client):
    """404 scans must not be able to grow the number of series without bound.

    Unknown paths are all matched by the SPA catch-all route, so they share its
    template. What matters is that scanning the app cannot mint new series: an
    attacker walking /api/aaa, /api/aab... would otherwise fill the time-series
    database on demand.
    """
    import re
    before = set(re.findall(r'route="([^"]*)"', _scrape(client)))
    for path in ("/api/nope-one", "/api/nope-two", "/api/nope-three", "/random/deep/path"):
        client.get(path)
    after = set(re.findall(r'route="([^"]*)"', _scrape(client)))

    assert not any("nope" in r for r in after), after
    # At most one new route label appeared (the catch-all), never one per path.
    assert len(after - before) <= 1, after - before


def test_status_code_is_recorded(client, seeded):
    login(client, "member@test")
    client.get("/api/admin/users")  # forbidden for a member
    body = _scrape(client)
    assert 'status="403"' in body


def test_login_outcomes_are_counted(client, seeded):
    before = _scrape(client)
    client.post("/api/auth/login", json={"email": "admin@test", "password": "wrong"})
    login(client, "admin@test")
    after = _scrape(client)
    assert 'teamfollowup_logins_total{outcome="failure"}' in after
    assert 'teamfollowup_logins_total{outcome="success"}' in after
    assert after != before


def test_scrape_does_not_appear_in_its_own_metrics(client):
    client.get("/metrics")
    body = _scrape(client)
    assert 'route="/metrics"' not in body


# ---- protection ----------------------------------------------------------------

def test_token_is_required_when_configured(client, monkeypatch):
    monkeypatch.setattr(settings, "metrics_token", "s3cret")
    assert client.get("/metrics").status_code == 401
    assert client.get("/metrics", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert client.get("/metrics", headers={"Authorization": "s3cret"}).status_code == 401
    ok = client.get("/metrics", headers={"Authorization": "Bearer s3cret"})
    assert ok.status_code == 200


def test_disabled_endpoint_answers_404(client, monkeypatch):
    monkeypatch.setattr(settings, "metrics_enabled", False)
    assert client.get("/metrics").status_code == 404


def test_authorization_helper_is_open_only_when_no_token(monkeypatch):
    monkeypatch.setattr(settings, "metrics_token", "")
    assert metrics_mod.metrics_authorized(None) is True
    monkeypatch.setattr(settings, "metrics_token", "  ")  # whitespace is not a token
    assert metrics_mod.metrics_authorized(None) is True
    monkeypatch.setattr(settings, "metrics_token", "abc")
    assert metrics_mod.metrics_authorized(None) is False
    assert metrics_mod.metrics_authorized("Basic abc") is False
    assert metrics_mod.metrics_authorized("bearer abc") is True  # scheme is case-insensitive


def test_metrics_endpoint_is_absent_from_the_openapi_contract(client):
    """It is an operations endpoint, not part of the product's API contract."""
    schema = client.get("/openapi.json").json()
    assert "/metrics" not in schema["paths"]
