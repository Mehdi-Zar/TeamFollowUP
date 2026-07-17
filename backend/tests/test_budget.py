"""Squad budget: role split (tribe sets the envelope, squad leader reports),
derived on-track/at-risk/over status, and strict per-squad visibility."""
from .conftest import login

YEAR = 2026


def _enable(client, squad_id):
    r = client.put(f"/api/squads/{squad_id}", json={"budget_enabled": True})
    assert r.status_code == 200, r.text


def test_tribe_sets_total_squad_leader_reports_and_status(seeded, client):
    sa = seeded["squad_a"]
    # Tribe leader enables budget and fixes the envelope.
    login(client, seeded["tribe"])
    _enable(client, sa)
    r = client.put(f"/api/squads/{sa}/budget?year={YEAR}", json={"total": 1000})
    assert r.status_code == 200, r.text
    assert r.json()["total"] == 1000

    # Squad leader reports spend/forecast; total must stay locked at 1000 even if sent.
    login(client, seeded["sl_a"])
    r = client.put(f"/api/squads/{sa}/budget?year={YEAR}",
                   json={"total": 9999, "spent": 300, "forecast": 500})
    assert r.status_code == 200, r.text  # regression: Decimal total must not 500
    b = r.json()
    assert b["total"] == 1000          # squad leader cannot move the envelope
    assert b["spent"] == 300 and b["forecast"] == 500
    assert b["status"] == "on_track"

    # Forecast at 95% -> at risk (before any overspend).
    r = client.put(f"/api/squads/{sa}/budget?year={YEAR}", json={"forecast": 950})
    assert r.json()["status"] == "at_risk"

    # Forecast over the envelope -> over, with overrun figures.
    r = client.put(f"/api/squads/{sa}/budget?year={YEAR}", json={"forecast": 1100})
    b = r.json()
    assert b["status"] == "over" and b["overrun"] == 100 and b["overrun_pct"] == 10


def test_status_falls_back_to_spent_when_no_forecast(seeded, client):
    sa = seeded["squad_a"]
    login(client, seeded["admin"])
    _enable(client, sa)
    r = client.put(f"/api/squads/{sa}/budget?year={YEAR}", json={"total": 1000, "spent": 1200})
    assert r.json()["status"] == "over"


def test_squad_leader_cannot_enable_or_edit_other_squad(seeded, client):
    sa, sb = seeded["squad_a"], seeded["squad_b"]
    login(client, seeded["tribe"])
    _enable(client, sa)
    _enable(client, sb)

    login(client, seeded["sl_a"])
    # Enabling/disabling budget is reserved to the tribe leader.
    assert client.put(f"/api/squads/{sa}", json={"budget_enabled": False}).status_code == 403
    # Cannot edit another squad's budget.
    assert client.put(f"/api/squads/{sb}/budget?year={YEAR}", json={"spent": 1}).status_code == 403


def test_budget_visibility_is_per_squad(seeded, client):
    sa = seeded["squad_a"]
    login(client, seeded["tribe"])
    _enable(client, sa)
    client.put(f"/api/squads/{sa}/budget?year={YEAR}", json={"total": 1000, "spent": 200})

    # Owner squad leader sees the figures.
    login(client, seeded["sl_a"])
    assert client.get(f"/api/squads/{sa}?year={YEAR}").json()["budget"] is not None

    # Another squad leader (same tribe) does NOT see this squad's budget.
    login(client, seeded["sl_b"])
    assert client.get(f"/api/squads/{sa}?year={YEAR}").json()["budget"] is None

    # A plain member does not see budget figures either.
    login(client, seeded["member"])
    assert client.get(f"/api/squads/{sa}?year={YEAR}").json()["budget"] is None

    # Admin and the tribe leader do see it.
    login(client, seeded["admin"])
    assert client.get(f"/api/squads/{sa}?year={YEAR}").json()["budget"] is not None


def test_budget_and_key_messages_in_squad_export(seeded, client):
    sa = seeded["squad_a"]
    # Budget: the tribe leader sets the envelope (allowed).
    login(client, seeded["tribe"])
    _enable(client, sa)
    client.put(f"/api/squads/{sa}/budget?year={YEAR}", json={"total": 12345, "spent": 4000, "forecast": 9000})
    # Key messages: stewarded by the squad's OWN leader only - the tribe leader is
    # now denied (assert_leads_squad).
    r_tribe = client.post(f"/api/squads/{sa}/key-messages?year={YEAR}", json={"kind": "alert", "text": "nope"})
    assert r_tribe.status_code == 403, r_tribe.text
    login(client, seeded["sl_a"])
    r = client.post(f"/api/squads/{sa}/key-messages?year={YEAR}", json={"kind": "risk", "text": "Vendor slipping"})
    assert r.status_code == 201, r.text

    # Tribe leader export: key message AND budget figures are present.
    login(client, seeded["tribe"])
    html_priv = client.get(f"/api/reports/dashboard.html?squad_id={sa}&year={YEAR}").text
    assert "Vendor slipping" in html_priv
    assert "12,345" in html_priv          # budget total is shown to a privileged viewer

    # Plain member export: key message stays, but budget figures are hidden.
    login(client, seeded["member"])
    html_member = client.get(f"/api/reports/dashboard.html?squad_id={sa}&year={YEAR}").text
    assert "Vendor slipping" in html_member
    assert "12,345" not in html_member
