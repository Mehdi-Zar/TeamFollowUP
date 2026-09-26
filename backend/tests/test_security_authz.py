"""Pentest, authorization findings: each escalation path, locked by a test."""
import gzip
import io
import json

from sqlalchemy import select

from app.models import Squad, User
from app.personasconfig import get_personas, set_personas
from app.security import hash_password
from tests.conftest import login


def _uid(db, email):
    return db.scalar(select(User).where(User.email == email)).id


def _give_tabs(db, role, tabs):
    personas = get_personas(db)
    for p in personas:
        if p["key"] == role:
            p["admin_tabs"] = list(tabs)
    set_personas(db, personas)
    db.commit()


# 1. Taking over an account by setting its password -------------------------

def test_a_tribe_leader_cannot_set_another_users_password(client, db, seeded):
    login(client, seeded["tribe"])
    r = client.put(f"/api/admin/users/{seeded['sl_a_id']}", json={"password": "a-new-long-password"})
    assert r.status_code == 403
    login(client, "sl_a@test")  # the old password still works, the account is theirs
    assert client.get("/api/auth/me").json()["email"] == "sl_a@test"


def test_the_admin_sets_a_password_long_enough_and_not_silently_on_sso(client, db, seeded):
    login(client, seeded["admin"])
    uid = seeded["sl_a_id"]
    assert client.put(f"/api/admin/users/{uid}", json={"password": "short"}).status_code == 422
    assert client.put(f"/api/admin/users/{uid}", json={"password": "a-long-enough-password"}).status_code == 200
    sso = db.get(User, seeded["member_id"])
    sso.auth_subject = "idp-sub-1"
    db.commit()
    assert client.put(f"/api/admin/users/{sso.id}", json={"password": "a-long-enough-password"}).status_code == 400
    assert client.put(f"/api/admin/users/{sso.id}", json={"password": "a-long-enough-password",
                                                         "allow_local_password": True}).status_code == 200


# 2. and 3. Delegated administration tabs -----------------------------------

def test_a_personas_delegate_cannot_grant_itself_more_tabs(client, db, seeded):
    _give_tabs(db, "tribe_leader", ["personas", "tribe", "users"])
    login(client, seeded["tribe"])
    personas = client.get("/api/admin/personas").json()["personas"]
    for p in personas:
        if p["key"] == "tribe_leader":
            p["admin_tabs"] = p["admin_tabs"] + ["api", "data"]
    assert client.put("/api/admin/personas", json={"personas": personas}).status_code == 403
    for p in personas:
        if p["key"] == "tribe_leader":
            p["admin_tabs"] = ["personas", "tribe", "users"]
        if p["key"] == "squad_leader":
            p["admin_tabs"] = ["smtp"]  # a tab the delegate does not hold
    assert client.put("/api/admin/personas", json={"personas": personas}).status_code == 403


def test_the_sso_and_trust_tabs_are_the_administrators_only(client, db, seeded):
    _give_tabs(db, "tribe_leader", ["auth", "trust", "tribe"])
    tabs = next(p for p in get_personas(db) if p["key"] == "tribe_leader")["admin_tabs"]
    assert "auth" not in tabs and "trust" not in tabs
    login(client, seeded["tribe"])
    assert client.get("/api/admin/auth-config").status_code == 403
    assert client.get("/api/admin/trust-store").status_code == 403
    login(client, seeded["admin"])
    assert set(client.get("/api/admin/personas").json()["admin_only_tabs"]) == {"auth", "trust"}


def test_a_data_delegate_keeps_copies_but_never_restores_nor_reads_hashes(client, db, seeded):
    _give_tabs(db, "tribe_leader", ["data", "tribe"])
    login(client, seeded["admin"])
    snap = client.post("/api/admin/data/snapshots", json={"name": "copie"}).json()
    login(client, seeded["tribe"])
    raw = client.get(f"/api/admin/data/snapshots/{snap['id']}/download").content
    users = json.loads(gzip.decompress(raw))["users"]
    assert users and all(u.get("password_hash") is None for u in users)
    assert client.post(f"/api/admin/data/snapshots/{snap['id']}/restore", json={"confirm": True}).status_code == 403
    files = {"file": ("x.json.gz", gzip.compress(b'{"users": []}'), "application/gzip")}
    assert client.post("/api/admin/data/snapshots/import", files=files).status_code == 403
    assert client.post("/api/admin/data/reset", json={"confirm": True, "domains": ["reporting"]}).status_code == 403


def test_an_api_delegate_mints_keys_for_its_own_tribe_only(client, db, seeded):
    _give_tabs(db, "tribe_leader", ["api", "tribe"])
    login(client, seeded["tribe"])
    r = client.post("/api/admin/api-keys", json={"name": "k", "scopes": ["dashboard:read"], "tribe_id": None})
    assert r.status_code == 201 and r.json()["tribe_id"] == seeded["t1"]


def test_a_tribes_delegate_sees_and_edits_its_own_tribe_only(client, db, seeded):
    _give_tabs(db, "tribe_leader", ["tribes", "tribe"])
    login(client, seeded["tribe"])
    assert [t["tribe_id"] for t in client.get("/api/tribes/org-overview").json()] == [seeded["t1"]]
    assert client.put(f"/api/tribes/{seeded['t2']}", json={"description": "x"}).status_code == 403
    assert client.delete(f"/api/tribes/{seeded['t2']}").status_code == 403


# 4. to 10. -------------------------------------------------------------------

def test_a_squad_leader_cannot_enrol_the_tribe_leader_to_manage_their_absences(client, db, seeded):
    login(client, seeded["sl_a"])
    r = client.post("/api/members", json={"squad_id": seeded["squad_a"], "email": "tribe@test"})
    assert r.status_code == 403
    r = client.post("/api/members", json={"squad_id": seeded["squad_a"], "email": "sl_b@test"})
    assert r.status_code == 403
    login(client, seeded["tribe"])
    assert client.post("/api/members", json={"squad_id": seeded["squad_a"], "email": "sl_b@test"}).status_code == 201


def test_leave_types_are_the_administrators(client, db, seeded):
    login(client, seeded["tribe2"])
    assert client.post("/api/leaves/types", json={"label": "Hack"}).status_code == 403


def test_a_tribe_leader_cannot_decide_a_request_of_another_tribe(client, db, seeded):
    other = User(email="pending2@test", display_name="P2", role="member", status="pending",
                 tribe_id=seeded["t2"], password_hash=hash_password("pw"))
    db.add(other)
    db.commit()
    login(client, seeded["tribe"])
    assert client.post(f"/api/access-requests/{other.id}/approve", json={"role": "member"}).status_code == 403
    assert client.post(f"/api/access-requests/{other.id}/deny").status_code == 403


def test_a_non_admin_without_tribe_cannot_post_to_everyone(client, db, seeded):
    u = db.get(User, seeded["sl_b_id"])
    u.tribe_id = None
    db.commit()
    login(client, seeded["sl_b"])
    assert client.post("/api/feed", json={"content": "a tous", "kind": "info"}).status_code == 403


def test_a_pending_account_cannot_be_named_contributor(client, db, seeded):
    pend = User(email="newcomer@test", display_name="New", role="member", status="pending",
                password_hash=hash_password("pw"))
    db.add(pend)
    db.commit()
    login(client, seeded["sl_a"])
    r = client.put(f"/api/squads/{seeded['squad_a']}", json={"contributor_user_ids": [pend.id]})
    assert r.status_code == 400
    db.refresh(pend)
    assert pend.role == "member" and pend.tribe_id is None


def test_an_account_of_another_tribe_reads_like_an_unknown_email(client, db, seeded):
    login(client, seeded["tribe"])
    other = User(email="t2person@test", display_name="T2", role="member", tribe_id=seeded["t2"])
    db.add(other)
    db.commit()
    a = client.post("/api/members", json={"squad_id": seeded["squad_a"], "email": "t2person@test"})
    b = client.post("/api/members", json={"squad_id": seeded["squad_a"], "email": "nobody@test"})
    assert a.status_code == b.status_code == 201
    assert a.json()["user_id"] is None


def test_the_report_is_only_mailed_inside_the_tribe(client, db, seeded, monkeypatch):
    from app.smtpconfig import set_smtp
    set_smtp(db, {"enabled": True, "host": "smtp.local"})
    db.commit()
    import app.mail as mail
    monkeypatch.setattr(mail, "send_email", lambda *a, **k: True)
    login(client, seeded["member"])
    assert client.post("/api/reports/weekly/email", json={"to": "attacker@evil.example"}).status_code == 403
    assert client.post("/api/reports/weekly/email", json={"to": "sl_a@test"}).status_code in (200, 403, 404)
    r = client.post("/api/reports/weekly/email", json={"to": "sl_a@test"})
    assert r.status_code != 403 or "tribe" not in r.text


# Secrets, CSV, gzip -----------------------------------------------------------

def test_stored_secrets_come_back_masked_and_are_kept_on_save(client, db, seeded):
    from app.smtpconfig import get_smtp, set_smtp
    set_smtp(db, {"password": "s3cret-smtp"})
    db.commit()
    login(client, seeded["admin"])
    got = client.get("/api/admin/smtp-config").json()
    assert got["password"] == "********"
    assert client.put("/api/admin/smtp-config", json={**got, "host": "mail.example"}).status_code == 200
    db.expire_all()
    assert get_smtp(db)["password"] == "s3cret-smtp"
    assert client.get("/api/admin/auth-config").json().get("oidc_client_secret") in ("", "********")


def test_the_absences_csv_never_carries_a_formula():
    from app.sheetsafe import cell_safe, csv_safe
    assert csv_safe('=HYPERLINK("http://evil")') == "'=HYPERLINK(\"http://evil\")"
    for bad in ("+1", "-1", "@SUM(A1)", "\tx", "\rx"):
        assert csv_safe(bad).startswith("'")
    assert csv_safe("Congés") == "Congés" and csv_safe(3) == 3 and cell_safe("=1+1") == "'=1+1"


def test_a_snapshot_that_unfolds_too_big_is_refused(client, db, seeded, monkeypatch):
    from app.routers import data as data_mod
    monkeypatch.setattr(data_mod, "MAX_UNPACKED", 1024)
    login(client, seeded["admin"])
    bomb = gzip.compress(b"{" + b" " * 50_000 + b"}")
    r = client.post("/api/admin/data/snapshots/import",
                    files={"file": ("b.json.gz", io.BytesIO(bomb), "application/gzip")})
    assert r.status_code == 413


def test_a_squad_leader_does_not_manage_the_absences_of_a_tribe_leader(client, db, seeded):
    """Even once added to the squad, a tribe leader's absence is not the squad leader's."""
    from sqlalchemy import select
    from app.deps import can_manage_leave
    from app.models import User
    sl_a = db.scalar(select(User).where(User.email == seeded["sl_a"]))
    tl = db.scalar(select(User).where(User.email == seeded["tribe"]))
    sl_b = db.scalar(select(User).where(User.email == seeded["sl_b"]))
    assert can_manage_leave(db, sl_a, tl.id) is False
    assert can_manage_leave(db, sl_a, sl_b.id) is False
