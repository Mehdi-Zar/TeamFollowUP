"""Admin > Data: erasing on purpose, and being able to undo it.

The old way to start over was a CLI that wiped everything and re-seeded a
hard-coded organisation. What an administrator actually needs is to erase a year
of entries while keeping the org chart, to take a copy before doing it, and to put
that copy back when the wrong line was clicked.

These tests are mostly about what must NOT be lost: the configuration, the
break-glass login, and the snapshots themselves.
"""
import gzip
import io
import json

from sqlalchemy import select

from app import datareset
from app.models import (AppSetting, DataSnapshot, Objective, Otd, RoadmapItem, Squad,
                        Tribe, User)
from tests.conftest import login


def _content(db, seeded):
    """A bit of everything, so a domain-by-domain erase has something to erase."""
    db.add(Objective(squad_id=seeded["squad_a"], year=2026, title="Objectif"))
    db.add(RoadmapItem(squad_id=seeded["squad_a"], year=2026, quarter=1, title="Jalon"))
    db.add(Otd(tribe_id=seeded["t1"], year=2026, title="Engagement"))
    db.add(AppSetting(key="smtp", value='{"host": "relay.internal"}'))
    db.commit()


# ---- the catalogue -------------------------------------------------------------

def test_domains_are_counted_before_anything_is_erased(client, db, seeded):
    """The confirmation shows real numbers, not a promise."""
    _content(db, seeded)
    login(client, "admin@test")
    out = client.get("/api/admin/data/domains").json()
    assert out["domains"]["roadmap"]["total"] == 1
    assert out["domains"]["objectives"]["total"] == 1
    assert out["domains"]["initiatives"]["total"] == 1
    assert out["domains"]["structure"]["total"] == 5      # 3 squads + 2 tribes
    # The configuration is named as out of reach rather than merely absent.
    assert "app_settings" in out["never_erased"]


def test_erasing_a_domain_drags_what_hangs_off_it(client, db, seeded):
    """Objectives carry the milestones that answer them: leaving orphans behind
    would be worse than the reset itself."""
    assert datareset.expand(["objectives"]) == ["roadmap", "objectives"]
    assert "reporting" in datareset.expand(["structure"])
    assert datareset.expand(["kpis"]) == ["kpis"]


def test_only_an_admin_may_erase(client, db, seeded):
    login(client, seeded["tribe"])
    assert client.get("/api/admin/data/domains").status_code == 403
    assert client.post("/api/admin/data/reset",
                       json={"domains": ["kpis"], "confirm": True}).status_code == 403


def test_a_reset_without_confirmation_is_refused(client, db, seeded):
    login(client, "admin@test")
    r = client.post("/api/admin/data/reset", json={"domains": ["roadmap"]})
    assert r.status_code == 400 and "confirm" in r.json()["detail"].lower()


# ---- erasing -------------------------------------------------------------------

def test_erasing_the_entries_keeps_the_organisation(client, db, seeded):
    """The reason this screen exists: a fresh year without retyping the org chart."""
    _content(db, seeded)
    login(client, "admin@test")
    r = client.post("/api/admin/data/reset",
                    json={"domains": ["objectives", "initiatives"], "confirm": True,
                          "snapshot_first": False})
    assert r.status_code == 200, r.text

    db.expire_all()
    assert db.scalars(select(Objective)).all() == []
    assert db.scalars(select(RoadmapItem)).all() == []      # implied by objectives
    assert db.scalars(select(Otd)).all() == []
    assert len(db.scalars(select(Squad)).all()) == 3        # untouched
    assert len(db.scalars(select(Tribe)).all()) == 2
    assert db.get(AppSetting, "smtp") is not None           # configuration survives


def test_a_full_wipe_keeps_the_configuration_and_the_break_glass_login(client, db, seeded):
    """Losing the SMTP settings with the data would lock the administrator out of
    the app they were tidying up, and losing every login would lock them out for good."""
    _content(db, seeded)
    login(client, "admin@test")
    r = client.post("/api/admin/data/reset",
                    json={"domains": ["structure", "users", "audit"], "confirm": True,
                          "snapshot_first": False})
    assert r.status_code == 200, r.text

    db.expire_all()
    assert db.scalars(select(Tribe)).all() == []
    assert db.get(AppSetting, "smtp") is not None
    remaining = db.scalars(select(User)).all()
    assert [u.email for u in remaining] == ["admin@local"]  # the break-glass account
    assert remaining[0].role == "admin"


def test_erasing_the_accounts_alone_works_too(client, db, seeded):
    """Le cas qui repondait 500 en production.

    Effacer les comptes sans effacer la structure laissait le garde-fou se
    declencher sur le schema (``squad_coleaders.user_id`` est NOT NULL) alors que
    ces lignes venaient d'etre supprimees, compte par compte, par la politique de
    suppression. Le test precedent choisissait « structure + comptes », ce qui
    rangeait la table dans le lot efface et masquait le probleme.
    """
    _content(db, seeded)
    sl_b = db.scalar(select(User).where(User.email == seeded["sl_b"]))
    login(client, seeded["tribe"])
    client.put(f"/api/squads/{seeded['squad_a']}", json={"co_leader_user_ids": [sl_b.id]})

    login(client, "admin@test")
    r = client.post("/api/admin/data/reset",
                    json={"domains": ["users"], "confirm": True, "snapshot_first": False})
    assert r.status_code == 200, r.text

    db.expire_all()
    assert [u.email for u in db.scalars(select(User)).all()] == ["admin@local"]
    squad = db.get(Squad, seeded["squad_a"])
    assert squad is not None                      # la squad survit
    assert squad.co_leaders == []                 # son co-responsable est parti avec son compte
    assert squad.leader_user_id is None           # le responsable aussi, detache
    assert len(db.scalars(select(Tribe)).all()) == 2


def test_erasing_the_accounts_keeps_the_snapshots_and_their_authors_detached(client, db, seeded):
    """Une sauvegarde survit a la disparition de qui l'a prise."""
    _content(db, seeded)
    login(client, "admin@test")
    snap = client.post("/api/admin/data/snapshots", json={"name": "avant"}).json()

    r = client.post("/api/admin/data/reset",
                    json={"domains": ["users"], "confirm": True, "snapshot_first": False})
    assert r.status_code == 200, r.text
    rows = client.get("/api/admin/data/snapshots").json()
    assert [s["id"] for s in rows] == [snap["id"]]


# ---- snapshots -----------------------------------------------------------------

def test_a_snapshot_then_a_restore_puts_everything_back(client, db, seeded):
    _content(db, seeded)
    login(client, "admin@test")
    snap = client.post("/api/admin/data/snapshots", json={"name": "Avant essai"}).json()
    assert snap["rows"] > 0 and snap["size_bytes"] > 0

    client.post("/api/admin/data/reset",
                json={"domains": ["structure"], "confirm": True, "snapshot_first": False})
    db.expire_all()
    assert db.scalars(select(Squad)).all() == []

    r = client.post(f"/api/admin/data/snapshots/{snap['id']}/restore",
                    json={"confirm": True, "snapshot_first": False})
    assert r.status_code == 200, r.text
    db.expire_all()
    assert len(db.scalars(select(Squad)).all()) == 3
    assert len(db.scalars(select(Objective)).all()) == 1
    assert db.scalars(select(Tribe)).all() != []


def test_restoring_keeps_the_ids_so_links_survive(client, db, seeded):
    """A restore is a rewind, not a merge: a milestone must still point at its squad."""
    _content(db, seeded)
    squad_id = seeded["squad_a"]
    login(client, "admin@test")
    snap = client.post("/api/admin/data/snapshots", json={"name": "ids"}).json()
    client.post("/api/admin/data/reset",
                json={"domains": ["structure"], "confirm": True, "snapshot_first": False})
    client.post(f"/api/admin/data/snapshots/{snap['id']}/restore",
                json={"confirm": True, "snapshot_first": False})

    db.expire_all()
    item = db.scalars(select(RoadmapItem)).first()
    assert item is not None and item.squad_id == squad_id
    assert db.get(Squad, squad_id) is not None


def test_a_restore_takes_a_safety_copy_first(client, db, seeded):
    """Restoring the wrong line is itself undoable."""
    _content(db, seeded)
    login(client, "admin@test")
    snap = client.post("/api/admin/data/snapshots", json={"name": "A"}).json()
    r = client.post(f"/api/admin/data/snapshots/{snap['id']}/restore", json={"confirm": True})
    assert r.json()["safety_snapshot_id"] is not None
    names = [s["name"] for s in client.get("/api/admin/data/snapshots").json()]
    assert any(n.startswith("Avant restauration") for n in names)


def test_a_reset_leaves_a_copy_behind_by_default(client, db, seeded):
    _content(db, seeded)
    login(client, "admin@test")
    r = client.post("/api/admin/data/reset", json={"domains": ["structure"], "confirm": True})
    assert r.json()["snapshot_id"] is not None
    # The snapshot store is never erased by a reset, or the copy would go with it.
    assert client.get("/api/admin/data/snapshots").json() != []


def test_a_snapshot_never_carries_the_configuration(client, db, seeded):
    """SMTP credentials and the snapshots themselves stay out of the payload."""
    _content(db, seeded)
    login(client, "admin@test")
    snap_id = client.post("/api/admin/data/snapshots", json={"name": "x"}).json()["id"]
    raw = client.get(f"/api/admin/data/snapshots/{snap_id}/download").content
    data = json.loads(gzip.decompress(raw).decode("utf-8"))
    assert "app_settings" not in data
    assert "data_snapshots" not in data
    assert "squads" in data


def test_a_downloaded_snapshot_can_be_uploaded_back(client, db, seeded):
    """The file is the stored bytes, so it moves between instances."""
    _content(db, seeded)
    login(client, "admin@test")
    snap_id = client.post("/api/admin/data/snapshots", json={"name": "portable"}).json()["id"]
    raw = client.get(f"/api/admin/data/snapshots/{snap_id}/download").content

    r = client.post("/api/admin/data/snapshots/import",
                    files={"file": ("copie.json.gz", raw, "application/gzip")})
    assert r.status_code == 201, r.text
    imported = r.json()
    assert imported["id"] != snap_id and imported["rows"] > 0

    client.post("/api/admin/data/reset",
                json={"domains": ["structure"], "confirm": True, "snapshot_first": False})
    client.post(f"/api/admin/data/snapshots/{imported['id']}/restore",
                json={"confirm": True, "snapshot_first": False})
    db.expire_all()
    assert len(db.scalars(select(Squad)).all()) == 3


def test_a_foreign_file_is_refused_at_upload_not_mid_restore(client, db, seeded):
    login(client, "admin@test")
    junk = gzip.compress(json.dumps({"pas_une_table": [1, 2]}).encode())
    r = client.post("/api/admin/data/snapshots/import",
                    files={"file": ("x.json.gz", junk, "application/gzip")})
    assert r.status_code == 400
    r = client.post("/api/admin/data/snapshots/import",
                    files={"file": ("x.json.gz", b"pas du gzip", "application/gzip")})
    assert r.status_code == 400


def test_deleting_a_snapshot_leaves_the_data_alone(client, db, seeded):
    _content(db, seeded)
    login(client, "admin@test")
    snap_id = client.post("/api/admin/data/snapshots", json={"name": "jetable"}).json()["id"]
    assert client.delete(f"/api/admin/data/snapshots/{snap_id}").status_code == 204
    assert client.get("/api/admin/data/snapshots").json() == []
    assert len(db.scalars(select(Squad)).all()) == 3


# ---- automatic snapshots --------------------------------------------------------

def test_automatic_snapshots_are_off_until_somebody_asks(client, db, seeded):
    from app.datasnapshots import run_due_snapshot

    login(client, "admin@test")
    assert client.get("/api/admin/data/snapshot-config").json()["enabled"] is False
    assert run_due_snapshot(db) is None
    assert db.scalars(select(DataSnapshot)).all() == []


def test_the_scheduler_takes_one_when_due_then_waits(client, db, seeded):
    from app.datasnapshots import run_due_snapshot

    login(client, "admin@test")
    client.put("/api/admin/data/snapshot-config",
               json={"enabled": True, "interval_days": 7, "keep": 2})
    assert run_due_snapshot(db) is not None
    assert run_due_snapshot(db) is None            # not due again for a week
    rows = db.scalars(select(DataSnapshot)).all()
    assert len(rows) == 1 and rows[0].kind == "auto"


def test_retention_prunes_automatic_copies_but_never_manual_ones(client, db, seeded):
    """Somebody took the manual one on purpose; only they should remove it."""
    from app.datasnapshots import create, prune

    login(client, "admin@test")
    create(db, "manuelle", kind="manual")
    for i in range(4):
        create(db, f"auto {i}", kind="auto")
    db.commit()

    assert prune(db, keep=2) == 2
    db.commit()
    remaining = db.scalars(select(DataSnapshot)).all()
    kinds = sorted(s.kind for s in remaining)
    assert kinds == ["auto", "auto", "manual"]
