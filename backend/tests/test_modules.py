from app.modulesconfig import get_modules, set_modules, is_active
from tests.conftest import login


# ---- config model --------------------------------------------------------------

def test_defaults_all_enabled(db, seeded):
    cfg = get_modules(db)
    assert cfg["feed"]["enabled"] is True
    assert cfg["feed"]["reactions"] is True
    assert is_active(cfg, "feed") is True
    assert is_active(cfg, "feed", "reactions") is True


def test_set_modules_sanitizes_and_persists(db, seeded):
    cfg = set_modules(db, {
        "feed": {"enabled": False, "reactions": False, "bogus": True},
        "unknown_module": {"enabled": True},
        "review": {"weekly_report": False},
    })
    db.commit()
    assert cfg["feed"]["enabled"] is False
    assert cfg["feed"]["reactions"] is False
    assert "bogus" not in cfg["feed"]
    assert "unknown_module" not in cfg
    assert cfg["review"]["weekly_report"] is False
    assert cfg["review"]["enabled"] is True  # untouched


def test_is_active_feature_requires_module(db, seeded):
    cfg = set_modules(db, {"feed": {"enabled": False, "reactions": True}})
    # Feature true but module off -> inactive.
    assert is_active(cfg, "feed", "reactions") is False
    assert is_active(cfg, "feed") is False


# ---- admin endpoints -----------------------------------------------------------

def test_admin_modules_roundtrip(client, seeded):
    login(client, seeded["admin"])
    assert client.get("/api/admin/modules-config").json()["feed"]["enabled"] is True
    out = client.put("/api/admin/modules-config", json={"feed": {"enabled": False}}).json()
    assert out["feed"]["enabled"] is False


def test_modules_config_forbidden_for_member(client, seeded):
    login(client, seeded["member"])
    assert client.get("/api/admin/modules-config").status_code == 403


def test_public_config_exposes_modules(client, seeded):
    assert "modules" in client.get("/api/config").json()


# ---- server-side enforcement ---------------------------------------------------

def _disable(client, patch):
    return client.put("/api/admin/modules-config", json=patch)


def test_disabling_feed_blocks_feed_api(client, seeded):
    login(client, seeded["admin"])
    assert client.get("/api/feed").status_code == 200
    _disable(client, {"feed": {"enabled": False}})
    assert client.get("/api/feed").status_code == 404


def test_disabling_feed_reactions_only(client, seeded):
    login(client, seeded["sl_a"])
    pid = client.post("/api/feed", json={"content": "x", "kind": "info"}).json()["id"]
    login(client, seeded["admin"])
    _disable(client, {"feed": {"reactions": False}})
    # Feed still up, but reactions blocked.
    assert client.get("/api/feed").status_code == 200
    login(client, seeded["sl_a"])
    assert client.post(f"/api/feed/{pid}/reactions", json={"kind": "like"}).status_code == 404
    assert client.post(f"/api/feed/{pid}/replies", json={"content": "hi"}).status_code == 201


def test_disabling_dashboard(client, seeded):
    login(client, seeded["admin"])
    assert client.get("/api/dashboard").status_code == 200
    _disable(client, {"dashboard": {"enabled": False}})
    assert client.get("/api/dashboard").status_code == 404


def test_disabling_exports_csv(client, seeded):
    login(client, seeded["admin"])
    _disable(client, {"exports_csv": {"enabled": False}})
    assert client.get("/api/exports/dashboard.csv").status_code == 404


def test_disabling_review_blocks_review_and_report(client, seeded):
    login(client, seeded["admin"])
    assert client.get("/api/progress/review").status_code == 200
    _disable(client, {"review": {"enabled": False}})
    assert client.get("/api/progress/review").status_code == 404
    assert client.get("/api/reports/weekly.html").status_code == 404


def test_disabling_weekly_report_only(client, seeded):
    login(client, seeded["admin"])
    _disable(client, {"review": {"weekly_report": False}})
    # Review still works, only the weekly report is gone.
    assert client.get("/api/progress/review").status_code == 200
    assert client.get("/api/reports/weekly.html").status_code == 404


def test_disabling_squad_content_objectives(client, seeded):
    sid = seeded["squad_a"]
    login(client, seeded["tribe"])  # objectives are managed by the tribe leader
    ok = client.post("/api/objectives", json={"squad_id": sid, "year": 2026, "title": "O", "rag_status": "green"})
    assert ok.status_code in (200, 201)
    login(client, seeded["admin"])
    _disable(client, {"squad_content": {"objectives": False}})
    login(client, seeded["tribe"])
    assert client.post("/api/objectives", json={"squad_id": sid, "year": 2026, "title": "O2", "rag_status": "green"}).status_code == 404


def test_disabling_org(client, seeded):
    login(client, seeded["admin"])
    assert client.get("/api/org").status_code == 200
    _disable(client, {"org": {"enabled": False}})
    assert client.get("/api/org").status_code == 404
