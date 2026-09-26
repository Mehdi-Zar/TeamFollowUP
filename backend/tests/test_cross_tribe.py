"""Reads and actions stay inside the caller's tribe.

Each case here was reachable by id: the list screens filtered by tribe, but the
routes behind a single item did not. A tribe leader deleted another tribe's post,
a member read another tribe's frozen reporting, and a tribe leader pulled a
revoked account of another tribe, or a former admin, into their own tribe."""
from app.models import FeedPost, ReportSnapshot, User
from tests.conftest import login


def test_snapshots_of_another_tribe_are_not_readable(client, db, seeded):
    snap = ReportSnapshot(squad_id=seeded["squad_c"], cycle_label="S39", payload={"objectives": []})
    db.add(snap)
    db.commit()
    login(client, seeded["member"])
    base = f"/api/squads/{seeded['squad_c']}/snapshots"
    assert client.get(base).status_code == 403
    assert client.get(f"{base}/{snap.id}").status_code == 403
    assert client.get(f"{base}/{snap.id}/compare").status_code == 403


def _post(db, tribe_id, author_email):
    author = db.query(User).filter_by(email=author_email).one()
    p = FeedPost(tribe_id=tribe_id, author_user_id=author.id, content="hello", kind="info")
    db.add(p)
    db.commit()
    return p.id


def test_feed_actions_do_not_reach_another_tribe(client, db, seeded):
    other = _post(db, seeded["t2"], seeded["tribe2"])
    login(client, seeded["tribe"])
    assert client.delete(f"/api/feed/{other}").status_code == 404
    assert client.put(f"/api/feed/{other}/pin", json={"is_pinned": True}).status_code == 404
    assert client.post(f"/api/feed/{other}/replies", json={"content": "x"}).status_code == 404
    assert client.post(f"/api/feed/{other}/reactions", json={"kind": "like"}).status_code == 404
    assert db.get(FeedPost, other) is not None


def test_global_post_is_moderated_by_the_admin_only(client, db, seeded):
    glob = _post(db, None, seeded["admin"])
    login(client, seeded["tribe"])
    post = next(p for p in client.get("/api/feed").json() if p["id"] == glob)
    assert post["can_delete"] is False and post["can_pin"] is False
    assert client.delete(f"/api/feed/{glob}").status_code == 403
    own = _post(db, seeded["t1"], seeded["sl_a"])
    post = next(p for p in client.get("/api/feed").json() if p["id"] == own)
    assert post["can_delete"] is True and post["can_pin"] is True
    assert client.delete(f"/api/feed/{own}").status_code == 204


def test_tribe_leader_does_not_reinstate_outside_their_tribe(client, db, seeded):
    victim = User(email="gone@test", display_name="Gone", role="member", tribe_id=seeded["t2"], status="disabled")
    old_admin = User(email="oldadmin@test", display_name="Old", role="admin", tribe_id=seeded["t1"], status="disabled")
    db.add_all([victim, old_admin])
    db.commit()
    login(client, seeded["tribe"])
    body = {"role": "member", "tribe_id": None, "squad_id": None}
    assert client.post(f"/api/access-requests/{victim.id}/approve", json=body).status_code == 403
    assert client.post(f"/api/access-requests/{old_admin.id}/approve", json=body).status_code == 403
    db.refresh(victim)
    assert victim.status == "disabled" and victim.tribe_id == seeded["t2"]


# ---- deletions that used to stop on a foreign key (500 on Postgres) -------------

def test_deleting_a_squad_keeps_what_others_hold_on_it(client, db, seeded):
    from app.models import ReportSubscription, RoadmapItem, Member
    dep = RoadmapItem(squad_id=seeded["squad_a"], title="Needs B", quarter=1, year=2026,
                      dependency_kind="squad", dependency_squad_id=seeded["squad_b"])
    boss = Member(squad_id=seeded["squad_b"], full_name="Boss")
    db.add_all([dep, boss])
    db.flush()
    db.add(Member(squad_id=seeded["squad_b"], full_name="Report", manager_id=boss.id))
    admin = db.query(User).filter_by(email=seeded["admin"]).one()
    db.add(ReportSubscription(user_id=admin.id, squad_id=seeded["squad_b"], interval_days=7))
    db.commit()
    login(client, seeded["admin"])
    r = client.delete(f"/api/squads/{seeded['squad_b']}")
    assert r.status_code == 204, r.text
    db.refresh(dep)
    assert dep.dependency_squad_id is None and dep.dependency_kind == "text"
    assert dep.dependencies == "Squad B"


def test_deleting_a_tribe_cleans_up_or_says_what_blocks(client, db, seeded):
    from app.models import ApiKey, FeedPost, Initiative, Squad
    t2 = seeded["t2"]
    db.query(Squad).filter_by(tribe_id=t2).delete()
    ini = Initiative(tribe_id=t2, title="Init", year=2026)
    db.add(ini)
    db.add(FeedPost(tribe_id=t2, content="bye", kind="info"))
    db.commit()
    login(client, seeded["admin"])
    assert client.delete(f"/api/tribes/{t2}").status_code == 409
    db.delete(ini)
    db.commit()
    assert client.delete(f"/api/tribes/{t2}").status_code == 204
    assert db.query(FeedPost).filter_by(tribe_id=t2).count() == 0
    assert db.query(ApiKey).filter_by(tribe_id=t2).count() == 0


# ---- references checked before they reach a foreign key -------------------------

def test_unknown_or_foreign_references_are_refused(client, db, seeded):
    login(client, seeded["admin"])

    item = {"squad_id": seeded["squad_a"], "title": "J", "theme": "T", "quarter": 1, "year": 2026}
    assert client.post("/api/roadmap-items", json={**item, "dependency_kind": "squad",
                                                   "dependency_squad_id": 999999}).status_code == 400
    ok = client.post("/api/roadmap-items", json=item)
    assert ok.status_code == 201, ok.text
    assert client.put(f"/api/roadmap-items/{ok.json()['id']}",
                      json={"dependency_kind": "tribe", "dependency_tribe_id": 999999}).status_code == 400

    org = {"tribe_id": seeded["t1"], "title": "Box"}
    assert client.post("/api/org", json={**org, "squad_id": 999999}).status_code == 400
    assert client.post("/api/org", json={**org, "squad_id": seeded["squad_c"]}).status_code == 400


def test_org_chart_refuses_a_loop(client, db, seeded):
    login(client, seeded["admin"])
    a = client.post("/api/org", json={"tribe_id": seeded["t1"], "title": "A"}).json()["id"]
    b = client.post("/api/org", json={"tribe_id": seeded["t1"], "title": "B", "parent_id": a}).json()["id"]
    assert client.put(f"/api/org/{a}", json={"parent_id": b}).status_code == 400
    assert len(client.get(f"/api/org?tribe_id={seeded['t1']}").json()) == 1
