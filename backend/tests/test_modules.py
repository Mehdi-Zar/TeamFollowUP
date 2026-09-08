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


def test_disabling_feed_kinds_is_enforced_by_the_api_not_only_the_screen(client, seeded):
    """`feed > kinds` used to be the one feature flag with no server-side effect.

    Its three siblings (reactions, replies, pin) each gate a route, so switching
    them off really removes the behaviour. `kinds` only hid the selector: a client
    could still post an "incident" and still filter on it, which makes the admin
    switch a suggestion rather than a decision about the data.
    """
    login(client, seeded["admin"])
    _disable(client, {"feed": {"kinds": False}})

    login(client, seeded["sl_a"])
    posted = client.post("/api/feed", json={"content": "still tagged?", "kind": "incident"})
    assert posted.status_code == 201, posted.text
    assert posted.json()["kind"] == "info"          # coerced, not stored as incident

    # And the filter stops slicing a taxonomy that no longer exists: asking for a
    # kind returns what an unfiltered call returns, rather than a subset carved out
    # of posts written before the switch was flipped.
    everything = client.get("/api/feed").json()
    assert client.get("/api/feed?kind=incident").json() == everything
    assert any(p["content"] == "still tagged?" for p in everything)


def test_feed_kinds_still_work_when_the_feature_is_on(client, seeded):
    login(client, seeded["sl_a"])
    posted = client.post("/api/feed", json={"content": "outage", "kind": "incident"})
    assert posted.json()["kind"] == "incident"
    assert [p["content"] for p in client.get("/api/feed?kind=incident").json()] == ["outage"]


def test_disabling_dashboard(client, seeded):
    login(client, seeded["admin"])
    assert client.get("/api/dashboard").status_code == 200
    _disable(client, {"dashboard": {"enabled": False}})
    assert client.get("/api/dashboard").status_code == 404


def test_disabling_review_blocks_report(client, seeded):
    login(client, seeded["admin"])
    assert client.get("/api/reports/weekly.html").status_code == 200
    _disable(client, {"review": {"enabled": False}})
    assert client.get("/api/reports/weekly.html").status_code == 404


def test_disabling_weekly_report_only(client, seeded):
    login(client, seeded["admin"])
    _disable(client, {"review": {"weekly_report": False}})
    # Only the weekly report is gated off.
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


def test_every_declared_feature_flag_is_enforced_somewhere_server_side():
    """A switch the server does not honour is a suggestion, not a setting.

    `feed > kinds` was exactly that: it hid the selector in the SPA and gated
    nothing, so a client could still post an "incident" with the feature off. Its
    three siblings each carry a `require_module` on their route.

    Two enforcement shapes are legitimate, and both count here:

      * `require_module(module, feature)` as a route dependency, when the feature
        owns whole endpoints (`pin`, `replies`, `reactions`, `overlap_alert`, ...);
      * `is_active(..., module, feature)` in the code that acts, when the feature
        governs a field or a side effect rather than a route (`feed > kinds`
        coercing the kind, `notifications > email` skipping the send).

    A feature matching neither is unenforced, and this fails until it is.
    """
    import re
    from pathlib import Path

    from app.modulesconfig import _defaults

    app_dir = Path(__file__).resolve().parent.parent / "app"
    sources = "\n".join(
        p.read_text(encoding="utf-8") for p in app_dir.rglob("*.py")
        if p.name not in ("modulesconfig.py", "deps.py")
    )

    unenforced = []
    for module, feats in _defaults().items():
        for feature in (k for k in feats if k != "enabled"):
            pair = rf'["\']{module}["\']\s*,\s*["\']{feature}["\']'
            # A bounded any-char run, not [^)]*: the first argument is usually
            # `get_modules(db)`, whose own closing paren would end the class.
            if not (re.search(r"require_module\(\s*" + pair, sources)
                    or re.search(r"is_active\(.{0,40}?" + pair, sources)):
                unenforced.append(f"{module}.{feature}")
    assert unenforced == [], (
        "feature flags with no server-side effect: " + ", ".join(unenforced)
        + ". Gate the route with require_module, or check is_active where it acts."
    )
