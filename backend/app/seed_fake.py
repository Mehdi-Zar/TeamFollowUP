"""Test fixture seed: the Cloud Platform tribe filled with rich FAKE data.

Keeps the example squad names but generates fake users, members, objectives,
milestones (jalons), OTD commitments, KPIs, quarter progress, snapshots (varied
freshness), an org chart, a live feed and a multi-week progress-review timeline -
so the app can be exercised end to end.

Dense on purpose: the yearly timeline exports are a layout, and a layout only
breaks under load. Nine milestones per squad of varied title lengths, quarters
that sometimes carry three, objectives wired to initiatives so the timeline has
several rows, one row of milestones serving no initiative, and five dated
commitments per squad reaching November and December. See
`tests/test_export_timeline_dense.py`, which holds that density in place.

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
    Initiative,
    Kpi,
    Member,
    Otd,
    Notification,
    Objective,
    OrgNode,
    QuarterProgress,
    ReportSnapshot,
    RoadmapItem,
    Squad,
    Tribe,
    User,
)
from .routers.snapshots import build_payload
from .security import hash_password

logger = logging.getLogger("trt.seed_fake")
PRESERVE_TABLES = {"app_settings"}
PASSWORD = "test"

TRIBE_NAME = "Cloud Platform"

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

# Un catalogue de jalons aux formes variees, parce qu'une frise ne se teste pas
# avec cinq titres de vingt caracteres: il y a ici des titres courts, des titres
# qui tiennent sur deux lignes dans leur boite, et un titre assez long pour etre
# coupe sur des points de suspension. Une squad en tire neuf, decales selon son
# rang, pour que deux squads voisines ne racontent pas la meme annee et qu'un
# trimestre porte parfois trois jalons plutot qu'un.
# (titre, trimestre, theme, stage)
JALON_CATALOG = [
    ("Cadrage & architecture", 1, "Landing Zones", "EA"),
    ("Mise en place du socle", 1, "Landing Zones", "EA"),
    ("Reprise des environnements historiques et decommissionnement du socle precedent",
     1, "Managed Services", "EA"),
    ("Industrialisation", 2, "Managed Services", "GA"),
    ("Ouverture du service aux equipes pilotes", 2, "Software Factory", "EA"),
    ("Chaine de deploiement continue et signature des artefacts", 2, "Software Factory", "GA"),
    ("Mise en production", 3, "Landing Zones", "GA"),
    ("Durcissement securite et revue des habilitations", 3, "Landing Zones", "GA"),
    ("Observabilite de bout en bout", 3, "Managed Services", "GA"),
    ("Bascule du trafic vers le nouveau socle", 4, "Managed Services", "GA"),
    ("Bilan & optimisation", 4, "Software Factory", "GA"),
    ("Passage a l'echelle sur l'ensemble des regions et cloture du programme annuel",
     4, "Software Factory", "GA"),
    ("Automatisation du provisioning", 2, "Landing Zones", "EA"),
    ("Catalogue de services publie", 3, "Managed Services", "EA"),
]
JALONS_PER_SQUAD = 9

# Les engagements OTD, dates et de longueurs variees. Le dernier tombe en
# decembre avec un titre long: c'est le cas ou plus rien ne tient a droite du
# repere sur la frise, et il n'existait dans aucun jeu de donnees.
# (titre, mois)
OTD_SPECS = [
    ("Premiere region secondaire ouverte", 1),
    ("Socle multi-cloud disponible", 2),
    ("Landing zones certifiees", 3),
    ("Portail self-service ouvert aux equipes", 4),
    ("Catalogue de services manages publie", 5),
    ("Chaine de deploiement continue generalisee a toute la tribu", 6),
    ("Observabilite unifiee", 7),
    ("Revue de securite annuelle", 8),
    ("Reversibilite demontree", 9),
    ("Bascule du trafic client sur la nouvelle plateforme", 10),
    ("Decommissionnement du socle historique", 11),
    ("Cloture budgetaire du programme et bilan annuel de la tribu", 12),
]
OTDS_PER_SQUAD = 5

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
    """Delete all business data before re-seeding, in reverse FK order.

    Preserves `app_settings` (admin config) and the break-glass admin login, so a
    reseed never locks the operator out or loses configuration.
    """
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
    """Wipe and regenerate the Cloud Platform tribe with rich fake data.

    Uses a fixed-seed RNG (Random(42)) so successive runs produce the same dataset
    - handy for reproducible tests/screenshots. Health per squad is driven by the
    PROFILES table. Not idempotent: it wipes business data first (see `_wipe`).
    """
    rng = random.Random(42)
    now = datetime.now(timezone.utc)
    year = now.year
    pw = hash_password(PASSWORD)

    def qdate(q: int, day: int = 15) -> datetime:
        """A date in the middle month of quarter `q` (Q1→Feb, Q2→May, …)."""
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
    squad_refs = []  # (squad, squad_type, objectives, jalons) - for initiatives/OTD wiring
    used_names = set()
    for order, (name, leader_name, slug, profile, domain) in enumerate(SQUADS, start=1):
        leader = User(email=f"{slug}@local", display_name=leader_name, role="squad_leader",
                      tribe_id=tribe.id, password_hash=pw, created_at=now)
        db.add(leader)
        db.flush()
        # Pilotage / Opérations squads are cross-cutting → transverse (initiatives/OTD);
        # the rest deliver a product roadmap.
        squad_type = "transverse" if domain in ("Pilotage", "Opérations") else "product"
        s = Squad(name=name, description=f"Squad {name} - {domain}.", tribe_id=tribe.id,
                  leader_user_id=leader.id, display_order=order, squad_type=squad_type)
        db.add(s)
        db.flush()
        squads.append((s, profile, domain, leader))
        prof = PROFILES[profile]

        # Objectives
        obj_titles = [
            f"Industrialiser {name}",
            f"Améliorer la fiabilité de {name}",
        ]
        squad_objectives = []
        for oi, (title, rag) in enumerate(zip(obj_titles, prof["objs"])):
            obj = Objective(squad_id=s.id, year=year, title=title, rag_status=rag, weight=2 - oi,
                            description=f"Objectif {oi+1} de la squad {name} pour l'année {year}.",
                            target_date=qdate(2 + oi))
            db.add(obj)
            squad_objectives.append(obj)
        db.flush()

        # Milestones (jalons) across quarters - grouped by reusable theme. La
        # tranche du catalogue tourne avec le rang de la squad, donc la forme de
        # la frise change d'une squad a l'autre: un trimestre charge ici, vide
        # la, ce qui est ce qu'une mise en page doit savoir encaisser.
        start = (order * 3) % len(JALON_CATALOG)
        picks = [JALON_CATALOG[(start + k) % len(JALON_CATALOG)] for k in range(JALONS_PER_SQUAD)]
        picks.sort(key=lambda p: p[1])
        squad_jalons = []
        for ji, (jt, q, theme, stage) in enumerate(picks):
            owner = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
            status = rng.choice(prof["jalon"])
            # Each milestone answers one of the squad's objectives (round-robin).
            # Le dernier n'en sert aucun, volontairement: c'est la ligne « sans
            # titre » de la frise, celle des jalons qui ne repondent a rien, et
            # elle ne se teste pas si aucun jeu de donnees ne la produit.
            obj_id = (None if ji == len(picks) - 1
                      else squad_objectives[ji % len(squad_objectives)].id)
            jal = RoadmapItem(
                squad_id=s.id, year=year, quarter=q, title=jt,
                theme=theme, release_stage=stage,
                status=status, display_order=ji, owner=owner,
                objective_id=obj_id,
                description=f"{jt} pour la squad {name}.",
                success_criteria="Critères de succès définis et validés avec les parties prenantes.",
                user_benefit="Bénéfice concret pour les utilisateurs et la fiabilité du service.",
                dependencies="Disponibilité des environnements et validation sécurité.",
                risks="Dépendances externes et fenêtres de maintenance." if status in ("at_risk", "blocked") else None,
            )
            db.add(jal)
            squad_jalons.append(jal)
        squad_refs.append((s, squad_type, squad_objectives, squad_jalons))

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

    # ---- Initiatives: a flat list set by the tribe leader, one assigned per squad
    # (owner + deadline), so each surfaces in its squad's report/dashboard.
    init_specs = [
        ("Portail self-service unifié", 9),
        ("Industrialisation multi-cloud", 11),
        ("Excellence opérationnelle & FinOps", 6),
        ("Sécurisation des landing zones", 3),
        ("Catalogue de services managés", 5),
        ("Observabilité unifiée", 8),
        ("Reversibilité et sortie de dépendance", 10),
        ("Socle de données de la tribe", 7),
        ("Automatisation du provisioning", 4),
        ("Conformité et souveraineté", 12),
        ("Réduction de la dette technique", 6),
        ("Expérience développeur", 9),
        ("Continuité de service et plan de reprise", 11),
        ("Maîtrise de la consommation cloud", 5),
    ]
    by_squad: dict[int, list[Initiative]] = {}
    for ii, (title, month) in enumerate(init_specs):
        s = squads[ii % len(squads)][0]
        owner = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
        ini = Initiative(tribe_id=tribe.id, year=year, title=title, squad_id=s.id,
                         owner=owner, deadline=datetime(year, month, 28, tzinfo=timezone.utc),
                         display_order=ii)
        db.add(ini)
        by_squad.setdefault(s.id, []).append(ini)
    db.flush()

    # Le chainage Initiative <- Objective <- Jalon est ce que la frise suit pour
    # faire ses lignes. Sans objectif rattache, tous les jalons tombaient dans la
    # ligne « sans titre » et la frise n'avait qu'une ligne, quel que soit le
    # nombre de jalons: de quoi croire une mise en page juste alors qu'elle
    # n'avait jamais rien eu a ranger.
    for sq, _stype, sq_objectives, _jalons in squad_refs:
        inis = by_squad.get(sq.id) or []
        for oi, obj in enumerate(sq_objectives):
            if inis:
                obj.initiative_id = inis[oi % len(inis)].id
    db.flush()

    # ---- Les engagements OTD: des promesses datees, fixees par le management et
    # servies par des jalons. Sans eux la bande du haut de la frise reste vide,
    # et c'est celle que le comite regarde en premier.
    otds = []
    for oi, (title, month) in enumerate(OTD_SPECS):
        otd = Otd(tribe_id=tribe.id, year=year, title=title, owner_user_id=tl.id,
                  budget_ref=f"BUD-{year}-{oi + 1:02d}", display_order=oi,
                  committed_date=datetime(year, month, 20, tzinfo=timezone.utc),
                  description=f"Engagement pris pour l'année {year} : {title.lower()}.")
        db.add(otd)
        otds.append((otd, month))
    db.flush()

    # Cinq engagements par squad, pris de deux en deux et decales d'une squad a
    # l'autre: pris a la suite, une squad sur deux heritait exactement du meme jeu
    # et la moitie des slides racontaient la meme annee. Un engagement est servi
    # par le jalon du trimestre ou il tombe, faute de quoi la bande du haut et la
    # roadmap du dessous donneraient deux calendriers differents.
    for si, (sq, _stype, _objs, jalons) in enumerate(squad_refs):
        for k in range(OTDS_PER_SQUAD):
            otd, month = otds[(si * 5 + k * 2) % len(otds)]
            q = (month - 1) // 3 + 1
            free = [j for j in jalons if j.otd_id is None]
            same_q = [j for j in free if j.quarter == q]
            target = (same_q or free)
            if target:
                target[0].otd_id = otd.id
    db.flush()

    # ---- Org chart (grouped by domain) ----
    root = OrgNode(tribe_id=tribe.id, parent_id=None, title="Direction de la tribe",
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
                 content="Revue trimestrielle Cloud Platform vendredi 14h - merci de préparer vos statuts.",
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
    logger.info("Fake data seedée : tribe '%s', %d squads, %d jalons, %d engagements OTD, "
                "%d initiatives, users/membres/KPIs/fil/frise. "
                "Mot de passe : '%s' (tribe leader : thomas.tl@local).",
                TRIBE_NAME, len(squads), len(squads) * JALONS_PER_SQUAD, len(OTD_SPECS),
                len(init_specs), PASSWORD)

def main() -> None:
    """Entry point for `python -m app.seed_fake`: run the fake seed in a session."""
    db = SessionLocal()
    try:
        run(db)
        logger.info("Seed de test terminé.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
