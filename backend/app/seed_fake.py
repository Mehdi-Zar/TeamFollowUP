"""Test fixture seed: the Cloud Foundations tribe filled with rich FAKE data.

Keeps the real squad names but generates fake users, members, objectives,
milestones (jalons), KPIs, quarter progress, snapshots (varied freshness), an
org chart, a live feed and a multi-week progress-review timeline — so the app
can be exercised end to end.

Wipes business data first (preserves app_settings config and the break-glass
admin). Run inside the app container:

    docker compose exec app python -m app.seed_fake
"""
import logging
import random
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .bootstrap import ensure_breakglass
from .config import settings
from .database import Base, SessionLocal
from .models import (
    FeedPost,
    FeedReaction,
    FeedReply,
    Kpi,
    Member,
    Notification,
    Objective,
    OrgNode,
    ProgressUpdate,
    QuarterProgress,
    ReportSnapshot,
    RoadmapItem,
    Squad,
    Tribe,
    User,
)
from .progress import compute_metrics
from .routers.snapshots import build_payload
from .security import hash_password

logger = logging.getLogger("trt.seed_fake")
PRESERVE_TABLES = {"app_settings"}
PASSWORD = "test"

TRIBE_NAME = "Cloud Foundations"

# (squad name, leader full name, email slug, health profile, domain)
SQUADS = [
    ("Portal", "Camille Durant", "camille.portal", "green", "Plateforme"),
    ("Managed Services", "Léo Marchand", "leo.managed", "amber", "Plateforme"),
    ("Azure", "Sara Dubois", "sara.azure", "green", "Cloud Providers"),
    ("GCP / S3NS", "Yanis Petit", "yanis.gcp", "red", "Cloud Providers"),
    ("AWS", "Emma Girard", "emma.aws", "green", "Cloud Providers"),
    ("VMware", "Paul Lemoine", "paul.vmware", "amber", "Cloud Providers"),
    ("Edge Computing", "Noah Blanc", "noah.edge", "red", "Cloud Providers"),
    ("Run & Operation", "Lina Faure", "lina.run", "amber", "Opérations"),
    ("Customer Success", "Tom Bernard", "tom.cs", "green", "Opérations"),
    ("Architecture", "Inès Marchand", "ines.archi", "green", "Pilotage"),
    ("Demand & Product Management", "Karim Belkacem", "karim.product", "amber", "Pilotage"),
    ("Vision & Strategie", "Nadia Khaldi", "nadia.vision", "green", "Pilotage"),
    ("Tribe Office", "Marc Olivier", "marc.office", "green", "Pilotage"),
]

# Pools of fake member identities to draw from.
FIRST = ["Hugo", "Julie", "Adam", "Chloé", "Sofiane", "Rania", "Yuki", "Marc",
         "Sophie", "Noé", "Alice", "Victor", "Manon", "Idris", "Clara", "Ethan",
         "Maya", "Léa", "Samir", "Jeanne", "Théo", "Nora", "Gabriel", "Inès"]
LAST = ["Renaud", "Lopez", "Schmitt", "Mercier", "Atallah", "Haddad", "Tanaka",
        "Roux", "Nguyen", "Bonnet", "Fontaine", "Da Silva", "Leroy", "Moreau",
        "Garcia", "Lambert", "Rousseau", "Benali", "Picard", "Henry"]
ROLE_TITLES = ["Ingénieur cloud", "SRE", "Data engineer", "Backend", "QA",
               "Product owner", "DevOps", "Architecte", "Analyste", "Tech lead"]

PROFILES = {
    # statuses pool weighted by health, quarter progress vector, obj rags, kpi trends
    "green": {
        "jalon": ["done", "done", "on_track", "on_track", "done"],
        "progress": (100, 75, 35, 5),
        "objs": ["green", "green"],
        "kpis": ["on_target", "on_target"],
        "conf": 4,
    },
    "amber": {
        "jalon": ["done", "on_track", "at_risk", "on_track", "at_risk"],
        "progress": (100, 55, 15, 0),
        "objs": ["amber", "green"],
        "kpis": ["under_pressure", "on_target"],
        "conf": 3,
    },
    "red": {
        "jalon": ["done", "blocked", "at_risk", "on_track", "blocked"],
        "progress": (90, 30, 5, 0),
        "objs": ["red", "amber"],
        "kpis": ["missed", "under_pressure"],
        "conf": 2,
    },
}


def _wipe(db: Session) -> None:
    bg = settings.breakglass_email.lower().strip()
    for table in reversed(Base.metadata.sorted_tables):
        if table.name in PRESERVE_TABLES:
            continue
        if table.name == "users":
            db.execute(table.delete().where(User.email != bg))
        else:
            db.execute(table.delete())
    db.commit()


def run(db: Session) -> None:
    rng = random.Random(42)
    now = datetime.now(timezone.utc)
    year = now.year
    pw = hash_password(PASSWORD)

    def qdate(q: int, day: int = 15) -> datetime:
        return datetime(year, (q - 1) * 3 + 2, day, tzinfo=timezone.utc)

    _wipe(db)
    ensure_breakglass(db)

    tribe = Tribe(name=TRIBE_NAME, description="Tribe socle cloud, plateformes et opérations.", display_order=1)
    db.add(tribe)
    db.flush()

    # Tribe leader + a couple of plain members at tribe level.
    tl = User(email="thomas.tl@local", display_name="Thomas Lefèvre", role="tribe_leader",
              tribe_id=tribe.id, password_hash=pw, created_at=now)
    db.add(tl)
    plain_members = []
    for i in range(3):
        u = User(email=f"membre{i+1}@local", display_name=f"{FIRST[i]} {LAST[i]}", role="member",
                 tribe_id=tribe.id, password_hash=pw, created_at=now)
        db.add(u)
        plain_members.append(u)
    db.flush()

    squads = []
    used_names = set()
    for order, (name, leader_name, slug, profile, domain) in enumerate(SQUADS, start=1):
        leader = User(email=f"{slug}@local", display_name=leader_name, role="squad_leader",
                      tribe_id=tribe.id, password_hash=pw, created_at=now)
        db.add(leader)
        db.flush()
        s = Squad(name=name, description=f"Squad {name} — {domain}.", tribe_id=tribe.id,
                  leader_user_id=leader.id, display_order=order)
        db.add(s)
        db.flush()
        squads.append((s, profile, domain, leader))
        prof = PROFILES[profile]

        # Objectives
        obj_titles = [
            f"Industrialiser {name}",
            f"Améliorer la fiabilité de {name}",
        ]
        for oi, (title, rag) in enumerate(zip(obj_titles, prof["objs"])):
            db.add(Objective(squad_id=s.id, year=year, title=title, rag_status=rag, weight=2 - oi,
                             description=f"Objectif {oi+1} de la squad {name} pour l'année {year}.",
                             target_date=qdate(2 + oi)))

        # Milestones (jalons) across quarters
        jalon_titles = [
            "Cadrage & architecture", "Mise en place du socle", "Industrialisation",
            "Mise en production", "Bilan & optimisation",
        ]
        quarters = [1, 2, 2, 3, 4]
        for ji, (jt, q, status) in enumerate(zip(jalon_titles, quarters, prof["jalon"])):
            owner = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
            db.add(RoadmapItem(
                squad_id=s.id, year=year, quarter=q, title=f"{jt} — {name}",
                status=status, display_order=ji, owner=owner,
                description=f"{jt} pour la squad {name}.",
                success_criteria="Critères de succès définis et validés avec les parties prenantes.",
                user_benefit="Bénéfice concret pour les utilisateurs et la fiabilité du service.",
                dependencies="Disponibilité des environnements et validation sécurité.",
                risks="Dépendances externes et fenêtres de maintenance." if status in ("at_risk", "blocked") else None,
            ))

        # Quarter progress
        comments = ["Cadrage terminé, socle posé.", "Industrialisation en cours.", None, None]
        for q, v, c in zip((1, 2, 3, 4), prof["progress"], comments):
            db.add(QuarterProgress(squad_id=s.id, year=year, quarter=q, progress_pct=v, comment=c))

        # KPIs
        kpi_defs = [
            ("Disponibilité", 99.95, 99.9, "%"),
            ("Délai de livraison", 6, 5, "j"),
        ]
        for (kname, cur, tgt, unit), trend in zip(kpi_defs, prof["kpis"]):
            db.add(Kpi(squad_id=s.id, name=kname, trend_status=trend, current_value=cur,
                       target_value=tgt, unit=unit, comment=f"Suivi {kname.lower()} de {name}."))

        # Members (3 each: the leader + 2 fake)
        people = [(leader_name, "Squad leader", leader.id)]
        for mi in range(2):
            fn = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
            people.append((fn, rng.choice(ROLE_TITLES), None))
        for mi, (fn, rt, uid) in enumerate(people):
            db.add(Member(squad_id=s.id, full_name=fn, role_title=rt, user_id=uid, display_order=mi))

    db.flush()

    # Member hierarchy: 3rd member reports to the 2nd, on a few squads.
    for s, *_ in squads[:5]:
        ms = sorted(s.members, key=lambda m: m.display_order)
        if len(ms) >= 3:
            ms[2].manager_id = ms[1].id
    db.flush()

    # ---- Org chart (grouped by domain) ----
    root = OrgNode(tribe_id=tribe.id, parent_id=None, title="Direction de la tribu",
                   person_name=tl.display_name, display_order=0)
    db.add(root)
    db.flush()
    domains: dict[str, list] = {}
    for s, profile, domain, leader in squads:
        domains.setdefault(domain, []).append((s, leader))
    for di, (dname, items) in enumerate(domains.items()):
        node = OrgNode(tribe_id=tribe.id, parent_id=root.id, title=dname, display_order=di)
        db.add(node)
        db.flush()
        for i, (s, leader) in enumerate(items):
            db.add(OrgNode(tribe_id=tribe.id, parent_id=node.id, title=s.name,
                           person_name=leader.display_name, squad_id=s.id, display_order=i))

    # ---- Snapshots (varied freshness; a few intentionally stale) ----
    threshold = settings.staleness_threshold_days
    for idx, (s, profile, domain, leader) in enumerate(squads):
        stale = idx % 5 == 0  # ~ every 5th squad is stale
        days_ago = threshold + 6 if stale else (idx % 4) + 1
        for label, delta in (("Soumission précédente", days_ago + 21), ("Dernière soumission", days_ago)):
            db.add(ReportSnapshot(squad_id=s.id, submitted_by_user_id=s.leader_user_id,
                                  submitted_at=now - timedelta(days=delta),
                                  payload=build_payload(s, year), cycle_label=label))

    # ---- Progress-review timeline ----
    _seed_timeline(db, squads, year, now)

    # ---- Feed (tweet zone) ----
    by_name = {s.name: (s, leader) for s, _, _, leader in squads}
    gcp_s, gcp_l = by_name["GCP / S3NS"]
    aws_s, aws_l = by_name["AWS"]
    portal_s, portal_l = by_name["Portal"]
    edge_s, edge_l = by_name["Edge Computing"]
    posts = [
        FeedPost(tribe_id=tribe.id, author_user_id=gcp_l.id, kind="incident", squad_id=gcp_s.id, is_pinned=True,
                 content="Incident sur l'ingestion GCP / S3NS : pipeline en pause, investigation en cours.",
                 created_at=now - timedelta(hours=3)),
        FeedPost(tribe_id=tribe.id, author_user_id=tl.id, kind="info",
                 content="Revue trimestrielle Cloud Foundations vendredi 14h — merci de préparer vos statuts.",
                 created_at=now - timedelta(hours=9)),
        FeedPost(tribe_id=tribe.id, author_user_id=aws_l.id, kind="success", squad_id=aws_s.id,
                 content="Migration FinOps AWS terminée : -12% sur la facture ce trimestre 🎉",
                 created_at=now - timedelta(days=1)),
        FeedPost(tribe_id=tribe.id, author_user_id=portal_l.id, kind="info", squad_id=portal_s.id,
                 content="Nouvelle version du Portal en recette la semaine prochaine.",
                 created_at=now - timedelta(hours=6)),
        FeedPost(tribe_id=tribe.id, author_user_id=edge_l.id, kind="incident", squad_id=edge_s.id,
                 content="Edge Computing : déploiement bloqué sur 2 sites, dépendance matérielle.",
                 created_at=now - timedelta(hours=20)),
    ]
    db.add_all(posts)
    db.flush()
    db.add(FeedReply(post_id=posts[0].id, author_user_id=tl.id,
                     content="Merci, tenez-moi au courant de l'ETA.", created_at=now - timedelta(hours=2)))
    db.add(FeedReply(post_id=posts[2].id, author_user_id=tl.id,
                     content="Bravo à l'équipe AWS !", created_at=now - timedelta(hours=20)))
    db.add(FeedReaction(post_id=posts[2].id, user_id=tl.id, kind="like"))
    db.add(FeedReaction(post_id=posts[0].id, user_id=tl.id, kind="ack"))

    # ---- A few unread notifications for a member persona ----
    if plain_members:
        m = plain_members[0]
        db.add(Notification(user_id=m.id, kind="tweet", actor_name=gcp_l.display_name,
                            excerpt="Incident sur l'ingestion GCP / S3NS…", link="/fil",
                            is_read=False, created_at=now - timedelta(hours=3)))

    db.commit()
    logger.info("Fake data seedée : tribe '%s', %d squads, users/membres/jalons/KPIs/fil/frise. "
                "Mot de passe : '%s' (tribe leader : thomas.tl@local).", TRIBE_NAME, len(squads), PASSWORD)


def _seed_timeline(db: Session, squads, year: int, now: datetime) -> None:
    n_points = 9
    for s, profile, domain, leader in squads:
        metrics = compute_metrics(s, year)
        cur_pct, total = metrics["progress_pct"], metrics["total_count"]
        cur_blocked, cur_at_risk, cur_done = metrics["blocked_count"], metrics["at_risk_count"], metrics["done_count"]
        base_conf = PROFILES[profile]["conf"]
        notes = [
            f"Avancement régulier sur {s.name}. Socle en place.",
            f"Point d'attention sur {s.name} : dépendances à lever." if profile != "green"
            else f"{s.name} sous contrôle, cible tenue.",
        ]
        prev_pct = 0
        for i in range(n_points):
            frac = (i + 1) / n_points
            pct = round(cur_pct * frac)
            done = round(cur_done * frac)
            blocked = cur_blocked if i >= n_points - 3 else 0
            at_risk = cur_at_risk if i >= n_points - 5 else max(0, cur_at_risk - 1)
            created = now - timedelta(days=(n_points - 1 - i) * 7 + 1, hours=9)
            changes = []
            if pct != prev_pct:
                changes.append({"kind": "quarter_pct", "label": "Q2", "from": prev_pct, "to": pct})
            kind, note, confidence, created_by = "weekly", None, None, None
            review_slots = {n_points - 1: 0, n_points - 4: 1}
            if i in review_slots and review_slots[i] < len(notes):
                kind = "review"
                note = notes[review_slots[i]]
                confidence = max(1, min(5, base_conf + (0 if i == n_points - 1 else -1)))
                created_by = s.leader_user_id
            db.add(ProgressUpdate(
                squad_id=s.id, year=year, created_at=created, created_by_user_id=created_by,
                kind=kind, note=note, confidence=confidence, progress_pct=pct,
                blocked_count=blocked, at_risk_count=at_risk, done_count=done,
                total_count=total, state=None, changes=changes,
            ))
            prev_pct = pct


def main() -> None:
    db = SessionLocal()
    try:
        run(db)
        logger.info("Seed de test terminé.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
