"""Squad governance meetings ("comitologie"): module gating, CRUD, permissions,
and exposure through the squad detail payload."""
from tests.conftest import login


def _enable(client):
    """Committees module is off by default; turn it on as admin."""
    login(client, "admin@test")
    r = client.put("/api/admin/modules-config", json={"committees": {"enabled": True}})
    assert r.status_code == 200, r.text
    assert r.json()["committees"]["enabled"] is True


def _committee_payload(squad_id, **over):
    base = dict(
        squad_id=squad_id, name="Comité de pilotage",
        objective="Arbitrer le budget et les priorités",
        frequency="weekly", day_of_week="tue", time_of_day="09:30",
        duration_minutes=60, participants="Squad + PO",
    )
    base.update(over)
    return base


def test_module_gate_blocks_when_disabled(client, seeded):
    login(client, seeded["admin"])
    # Module off by default -> 404 (indistinguishable from non-existent).
    assert client.post("/api/committees", json=_committee_payload(seeded["squad_a"])).status_code == 404


def test_full_crud_and_squad_detail_exposure(client, seeded):
    _enable(client)
    login(client, seeded["admin"])

    created = client.post("/api/committees", json=_committee_payload(seeded["squad_a"]))
    assert created.status_code == 201, created.text
    cid = created.json()["id"]
    assert created.json()["frequency"] == "weekly"
    assert created.json()["day_of_week"] == "tue"

    # Surfaced on the squad detail page (visible to the tribe leader for oversight).
    login(client, seeded["tribe"])
    detail = client.get(f"/api/squads/{seeded['squad_a']}").json()
    assert any(c["id"] == cid and c["name"] == "Comité de pilotage" for c in detail["committees"])

    # Update + deactivate.
    login(client, seeded["admin"])
    upd = client.put(f"/api/committees/{cid}", json={"frequency": "monthly", "is_active": False})
    assert upd.status_code == 200, upd.text
    assert upd.json()["frequency"] == "monthly" and upd.json()["is_active"] is False

    # Delete.
    assert client.delete(f"/api/committees/{cid}").status_code == 204
    detail = client.get(f"/api/squads/{seeded['squad_a']}").json()
    assert all(c["id"] != cid for c in detail["committees"])


def test_squad_leader_scope_and_member_forbidden(client, seeded):
    _enable(client)

    # Squad leader A may declare committees for their own squad...
    login(client, seeded["sl_a"])
    r = client.post("/api/committees", json=_committee_payload(seeded["squad_a"], name="Daily A"))
    assert r.status_code == 201, r.text

    # ...but not for another squad.
    r = client.post("/api/committees", json=_committee_payload(seeded["squad_b"], name="Nope"))
    assert r.status_code == 403, r.text

    # Members cannot write.
    login(client, seeded["member"])
    assert client.post("/api/committees", json=_committee_payload(seeded["squad_a"])).status_code == 403


def test_unknown_squad_404(client, seeded):
    _enable(client)
    login(client, seeded["admin"])
    assert client.post("/api/committees", json=_committee_payload(999999)).status_code == 404


def test_per_sprint_and_other_frequency(client, seeded):
    _enable(client)
    login(client, seeded["admin"])

    # "per_sprint" is a valid frequency.
    r = client.post("/api/committees", json=_committee_payload(
        seeded["squad_a"], name="Sprint review", frequency="per_sprint", day_of_week=None))
    assert r.status_code == 201, r.text
    assert r.json()["frequency"] == "per_sprint"

    # "other" carries a free-text cadence.
    r = client.post("/api/committees", json=_committee_payload(
        seeded["squad_a"], name="Ad hoc", frequency="other",
        frequency_other="Tous les 10 jours ouvrés", day_of_week=None))
    assert r.status_code == 201, r.text
    assert r.json()["frequency"] == "other"
    assert r.json()["frequency_other"] == "Tous les 10 jours ouvrés"

    # An unknown frequency is rejected by validation.
    bad = client.post("/api/committees", json=_committee_payload(
        seeded["squad_a"], name="Bad", frequency="fortnightly"))
    assert bad.status_code == 422
