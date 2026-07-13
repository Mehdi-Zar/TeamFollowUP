"""API keys: minting, scope enforcement, tribe scoping, revocation, lifecycle.

The contract these tests pin down:
  * a key reads only what its scopes name, and only in its tribe;
  * a key is NOT a passport to the rest of the API (writes, admin, non-opted routes);
  * the secret is shown once and never stored in clear;
  * budgets require an explicit scope, even for a cross-tribe key.
"""
from tests.conftest import login


def _mint(client, seeded, **over):
    """Create a key as admin and return (public_dict, plaintext_secret)."""
    login(client, seeded["admin"])
    payload = {"name": "BI", "scopes": ["dashboard:read"]}
    payload.update(over)
    r = client.post("/api/admin/api-keys", json=payload)
    assert r.status_code == 201, r.text
    body = r.json()
    client.post("/api/auth/logout")
    return body, body["secret"]


def _auth(secret):
    return {"Authorization": f"Bearer {secret}"}


# ----- minting ---------------------------------------------------------------

def test_secret_is_returned_once_and_never_stored_in_clear(client, seeded, db):
    body, secret = _mint(client, seeded)
    assert secret.startswith("trt_")
    assert body["prefix"] in secret

    from app.models import ApiKey
    row = db.query(ApiKey).filter(ApiKey.prefix == body["prefix"]).one()
    assert secret not in row.key_hash          # stored hashed…
    assert row.key_hash.startswith("$argon2")  # …with argon2

    # The listing never echoes the secret back.
    login(client, seeded["admin"])
    listed = client.get("/api/admin/api-keys").json()["keys"]
    assert all("secret" not in k for k in listed)


def test_only_admin_may_manage_keys(client, seeded):
    login(client, seeded["tribe"])
    assert client.get("/api/admin/api-keys").status_code == 403
    assert client.post("/api/admin/api-keys",
                       json={"name": "x", "scopes": ["dashboard:read"]}).status_code == 403


def test_a_key_needs_a_name_and_at_least_one_scope(client, seeded):
    login(client, seeded["admin"])
    assert client.post("/api/admin/api-keys", json={"name": "", "scopes": ["dashboard:read"]}).status_code == 400
    assert client.post("/api/admin/api-keys", json={"name": "x", "scopes": []}).status_code == 400
    # Unknown scopes are dropped, so a bogus-only list is an empty list.
    assert client.post("/api/admin/api-keys", json={"name": "x", "scopes": ["root:all"]}).status_code == 400


# ----- authentication --------------------------------------------------------

def test_key_authenticates_without_any_cookie(client, seeded):
    _, secret = _mint(client, seeded)
    r = client.get("/api/reports/dashboard.html?since_days=7", headers=_auth(secret))
    assert r.status_code == 200


def test_garbage_and_unknown_keys_are_401(client, seeded):
    for bad in ("garbage", "trt_dead_beef", "Bearer", ""):
        r = client.get("/api/reports/dashboard.html", headers={"Authorization": f"Bearer {bad}"})
        assert r.status_code == 401, bad


def test_no_credential_at_all_is_still_401(client):
    assert client.get("/api/reports/dashboard.html").status_code == 401


# ----- scopes ----------------------------------------------------------------

def test_scope_is_enforced_per_resource(client, seeded):
    _, secret = _mint(client, seeded, scopes=["dashboard:read"])
    # The scope it has…
    assert client.get("/api/reports/dashboard.html", headers=_auth(secret)).status_code == 200
    # …and the ones it does not.
    assert client.get("/api/reports/roadmap.html", headers=_auth(secret)).status_code == 403
    assert client.get("/api/reports/weekly.html", headers=_auth(secret)).status_code == 403


def test_key_is_not_a_passport_to_the_rest_of_the_api(client, seeded):
    """The whole point: a key opens the routes that opted in, and nothing else."""
    _, secret = _mint(client, seeded, scopes=["dashboard:read", "roadmap:read",
                                              "reports:read", "org:read", "budget:read"])
    h = _auth(secret)
    # Not the admin surface,
    assert client.get("/api/admin/api-keys", headers=h).status_code == 401
    assert client.get("/api/admin/personas", headers=h).status_code == 401
    # not the write surface,
    assert client.post("/api/tribes", json={"name": "Pwned"}, headers=h).status_code == 401
    # not even read routes that never opted in.
    assert client.get("/api/leaves", headers=h).status_code == 401
    assert client.get("/api/feed", headers=h).status_code == 401
    # And it cannot manage its own kind.
    assert client.post("/api/admin/api-keys",
                       json={"name": "self", "scopes": ["dashboard:read"]},
                       headers=h).status_code == 401


# ----- budgets ---------------------------------------------------------------

def test_budget_needs_its_own_scope_even_for_a_cross_tribe_key(client, seeded, db):
    """A key with no tribe reads every tribe - it must not collect budgets for free."""
    from app import status as st
    from app.models import Squad, SquadBudget
    squad = db.get(Squad, seeded["squad_a"])
    squad.budget_enabled = True
    db.add(SquadBudget(squad_id=squad.id, year=st.current_year_quarter()[0],
                       total=987654, spent=1000, forecast=2000))
    db.commit()

    # The renderer formats amounts (thin spaces, k€…), so assert on the budget
    # block itself rather than on the raw digits.
    _, plain = _mint(client, seeded, scopes=["dashboard:read"])
    html = client.get("/api/reports/dashboard.html?since_days=7", headers=_auth(plain)).text
    assert "udget" not in html   # no budget:read → the whole block is stripped

    _, with_budget = _mint(client, seeded, name="BI+budget",
                           scopes=["dashboard:read", "budget:read"])
    html2 = client.get("/api/reports/dashboard.html?since_days=7",
                       headers=_auth(with_budget)).text
    assert "udget" in html2      # budget:read → the block is served


# ----- tribe scoping ---------------------------------------------------------

def test_key_bound_to_a_tribe_cannot_read_another_tribe(client, seeded):
    foreign = seeded["squad_c"]  # squad of tribe t2

    _, scoped = _mint(client, seeded, name="tribe-scoped", scopes=["dashboard:read"],
                      tribe_id=seeded["t1"])
    r = client.get(f"/api/reports/dashboard.html?squad_id={foreign}", headers=_auth(scoped))
    assert r.status_code == 404  # out of scope → invisible, not merely forbidden

    _, global_key = _mint(client, seeded, name="global", scopes=["dashboard:read"])
    r = client.get(f"/api/reports/dashboard.html?squad_id={foreign}", headers=_auth(global_key))
    assert r.status_code == 200


# ----- lifecycle -------------------------------------------------------------

def test_revoked_key_stops_working_immediately(client, seeded):
    body, secret = _mint(client, seeded)
    assert client.get("/api/reports/dashboard.html", headers=_auth(secret)).status_code == 200

    login(client, seeded["admin"])
    assert client.post(f"/api/admin/api-keys/{body['id']}/revoke").status_code == 200
    client.post("/api/auth/logout")

    assert client.get("/api/reports/dashboard.html", headers=_auth(secret)).status_code == 401


def test_expired_key_is_refused(client, seeded, db):
    from datetime import timedelta

    from app.models import ApiKey, utcnow
    body, secret = _mint(client, seeded)
    row = db.query(ApiKey).filter(ApiKey.prefix == body["prefix"]).one()
    row.expires_at = utcnow() - timedelta(seconds=1)
    db.commit()

    assert client.get("/api/reports/dashboard.html", headers=_auth(secret)).status_code == 401


def test_last_used_at_is_recorded(client, seeded, db):
    from app.models import ApiKey
    body, secret = _mint(client, seeded)
    assert body["last_used_at"] is None

    client.get("/api/reports/dashboard.html", headers=_auth(secret))
    db.expire_all()
    row = db.query(ApiKey).filter(ApiKey.prefix == body["prefix"]).one()
    assert row.last_used_at is not None


def test_creation_and_revocation_are_audited(client, seeded, db):
    from app.models import AuditLog
    body, _ = _mint(client, seeded)
    login(client, seeded["admin"])
    client.post(f"/api/admin/api-keys/{body['id']}/revoke")

    actions = [a.action for a in db.query(AuditLog).all()]
    assert "api_key.create" in actions
    assert "api_key.revoke" in actions
