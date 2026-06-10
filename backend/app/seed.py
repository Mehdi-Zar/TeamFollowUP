"""Idempotent demo seed: 9 squads, annual objectives (set by the tribe leader),
quarterly roadmap, progress cursors, KPIs, squad members, and an editable global
org chart. Two squads are intentionally stale.
"""
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .models import (
    Kpi,
    Member,
    Objective,
    OrgNode,
    QuarterProgress,
    ReportSnapshot,
    RoadmapItem,
    Squad,
    Tribe,
    User,
)
from .security import hash_password
from .routers.snapshots import build_payload

logger = logging.getLogger("trt.seed")
SEED_MARKER_EMAIL = "marie.tribe@local"


def already_seeded(db: Session) -> bool:
    return db.scalar(select(User).where(User.email == SEED_MARKER_EMAIL)) is not None


def run_seed(db: Session) -> None:
    if not settings.seed_demo:
        logger.info("SEED_DEMO=false : seed ignoré.")
        return
    if already_seeded(db):
        logger.info("Données de démonstration déjà présentes : seed idempotent ignoré.")
        return

    now = datetime.now(timezone.utc)
    year = now.year
    pw = hash_password("demo")

    # ---- Tribes (tenants) ----
    tribe_a = Tribe(name="Plateforme & Paiements", description="Socle technique, cloud et paiements", display_order=1)
    tribe_b = Tribe(name="Produit & Data", description="Expérience produit et valorisation de la donnée", display_order=2)
    db.add_all([tribe_a, tribe_b])
    db.flush()

    def mk_user(email, name, role, tribe=None):
        u = User(email=email, display_name=name, role=role, password_hash=pw, created_at=now,
                 tribe_id=tribe.id if tribe else None)
        db.add(u)
        return u

    marie = mk_user("marie.tribe@local", "Marie Adjoint", "admin")  # global admin
    nadia = mk_user("nadia.n1@local", "Nadia Khaldi", "tribe_leader", tribe_a)
    karim = mk_user("karim.tribe@local", "Karim Belkacem", "tribe_leader", tribe_b)
    # squad leaders, each in their tribe
    leaders = {
        "aws": mk_user("leo.aws@local", "Léo Martin", "squad_leader", tribe_a),
        "gcp": mk_user("sara.gcp@local", "Sara Dubois", "squad_leader", tribe_a),
        "azure": mk_user("kevin.azure@local", "Kevin Roy", "squad_leader", tribe_a),
        "paiements": mk_user("ana.paiements@local", "Ana Costa", "squad_leader", tribe_a),
        "secu": mk_user("paul.secu@local", "Paul Lemoine", "squad_leader", tribe_a),
        "onboarding": mk_user("tom.onboarding@local", "Tom Bernard", "squad_leader", tribe_b),
        "support": mk_user("lina.support@local", "Lina Faure", "squad_leader", tribe_b),
        "dataplat": mk_user("yanis.data@local", "Yanis Petit", "squad_leader", tribe_b),
        "analytics": mk_user("emma.analytics@local", "Emma Girard", "squad_leader", tribe_b),
    }
    hugo = mk_user("hugo.member@local", "Hugo Renaud", "member", tribe_a)  # membre de la tribu A
    db.flush()

    order = [0]

    def squad(name, lead_key, desc, tribe):
        order[0] += 1
        s = Squad(name=name, description=desc, leader_user_id=leaders[lead_key].id, display_order=order[0],
                  tribe_id=tribe.id)
        db.add(s)
        return s

    aws = squad("AWS", "aws", "Plateforme et services AWS", tribe_a)
    gcp = squad("GCP", "gcp", "Plateforme et services Google Cloud", tribe_a)
    azure = squad("Azure", "azure", "Plateforme et services Microsoft Azure", tribe_a)
    paiements = squad("Paiements", "paiements", "Encaissement et réconciliation", tribe_a)
    secu = squad("Sécurité", "secu", "Sécurité applicative et conformité", tribe_a)
    onboarding = squad("Onboarding", "onboarding", "Parcours d'entrée client", tribe_b)
    support = squad("Support produit", "support", "Relation et succès client", tribe_b)
    dataplat = squad("Data Platform", "dataplat", "Pipelines et socle data", tribe_b)
    analytics = squad("Analytics", "analytics", "Reporting et décisionnel", tribe_b)
    db.flush()

    all_squads = [aws, gcp, azure, paiements, onboarding, support, dataplat, analytics, secu]

    def obj(s, title, rag, w=1):
        db.add(Objective(squad_id=s.id, year=year, title=title, rag_status=rag, weight=w))

    _jmap = {"planned": "on_track", "in_progress": "on_track", "done": "done", "at_risk": "at_risk", "late": "blocked"}

    def jal(s, q, title, status, o=0, owner=None, benefit=None, desc=None, success=None, deps=None, risks=None):
        db.add(RoadmapItem(squad_id=s.id, year=year, quarter=q, title=title,
                           status=_jmap.get(status, status), display_order=o,
                           owner=owner, user_benefit=benefit, description=desc,
                           success_criteria=success, dependencies=deps, risks=risks))

    def prog(s, q1, q2, q3, q4):
        for q, v in zip((1, 2, 3, 4), (q1, q2, q3, q4)):
            db.add(QuarterProgress(squad_id=s.id, year=year, quarter=q, progress_pct=v))

    def kpi(s, name, trend, cur=None, tgt=None, unit=None):
        db.add(Kpi(squad_id=s.id, name=name, trend_status=trend, current_value=cur, target_value=tgt, unit=unit))

    def members(s, people):
        for i, (name, role_title, user_id) in enumerate(people):
            db.add(Member(squad_id=s.id, full_name=name, role_title=role_title, user_id=user_id, display_order=i))

    # AWS — tenu
    obj(aws, "Optimiser le coût de la facture AWS", "green")
    obj(aws, "Migrer 80% des charges en managé", "green")
    jal(aws, 1, "Audit FinOps", "done", owner="Hugo Renaud")
    jal(aws, 2, "Reserved instances", "done", owner="Camille Roux")
    jal(aws, 2, "Tagging des ressources", "in_progress", owner="Hugo Renaud",
        desc="Standardiser le tagging de toutes les ressources AWS (équipe, environnement, coût).",
        success="100% des ressources taguées et conformes à la politique FinOps.",
        benefit="Refacturation précise par squad et meilleure visibilité des coûts.",
        deps="Politique de tagging validée par la Sécurité.",
        risks="Ressources legacy difficiles à taguer sans interruption de service.")
    jal(aws, 3, "Auto-scaling avancé", "planned", owner="Camille Roux")
    prog(aws, 100, 70, 10, 0)
    kpi(aws, "Disponibilité", "on_target", 99.98, 99.9, "%")
    members(aws, [("Léo Martin", "Squad leader", leaders["aws"].id), ("Hugo Renaud", "Ingénieur cloud", hugo.id),
                  ("Camille Roux", "SRE", None)])

    # GCP — rouge
    obj(gcp, "Mettre en place le data lake GCP", "amber", 2)
    jal(gcp, 1, "POC BigQuery", "done", owner="Noah Blanc")
    jal(gcp, 2, "Pipeline d'ingestion", "late", owner="Noah Blanc",
        desc="Pipeline d'ingestion temps réel des événements vers BigQuery.",
        success="Ingestion < 4h de bout en bout, 99% de complétude.",
        benefit="Données fraîches pour le reporting décisionnel.",
        deps="Ouverture réseau vers l'amont (équipe Infra) — bloquée.",
        risks="Dépendance réseau non résolue : tout le quarter est à l'arrêt.")
    jal(gcp, 2, "IAM et cloisonnement", "at_risk", owner="Sara Dubois",
        desc="Cloisonnement des accès par projet GCP.",
        risks="Modèle d'habilitation pas encore validé par la Sécurité.")
    jal(gcp, 3, "Mise en production", "planned")
    prog(gcp, 90, 30, 0, 0)
    kpi(gcp, "Latence d'ingestion", "missed", 12, 4, "h")
    members(gcp, [("Sara Dubois", "Squad leader", leaders["gcp"].id),
                  ("Noah Blanc", "Data engineer", None), ("Yuki Tanaka", "Data engineer", None)])

    # Azure — tenu, périmé
    obj(azure, "Sécuriser les identités (Entra ID)", "green")
    jal(azure, 1, "Connecteur SSO", "done"); jal(azure, 2, "MFA généralisé", "in_progress")
    prog(azure, 100, 50, 0, 0)
    kpi(azure, "Couverture MFA", "on_target", 88, 80, "%")
    members(azure, [("Kevin Roy", "Squad leader", leaders["azure"].id), ("Inès Marchand", "Ingénieure cloud", None)])

    # Paiements — rouge (objectif rouge)
    obj(paiements, "Réduire le taux d'échec sous 1%", "red", 3)
    obj(paiements, "Migrer vers le nouveau PSP", "amber")
    jal(paiements, 1, "Connecteur PSP v2", "done", owner="Marc Olivier")
    jal(paiements, 2, "Bascule progressive", "at_risk", owner="Ana Costa",
        desc="Bascule progressive du trafic vers le nouveau PSP (10% → 100%).",
        success="100% du trafic basculé sans hausse du taux d'échec.",
        benefit="Réduction des coûts de transaction et meilleure résilience.",
        deps="Validation conformité PCI-DSS.",
        risks="Incident PSP récurrent qui freine la montée en charge.")
    prog(paiements, 100, 55, 5, 0)
    kpi(paiements, "Taux d'échec paiement", "missed", 1.8, 1.0, "%")
    kpi(paiements, "Latence autorisation", "under_pressure", 420, 300, "ms")
    members(paiements, [("Ana Costa", "Squad leader", leaders["paiements"].id),
                        ("Marc Olivier", "Backend", None), ("Sophie Nguyen", "QA", None)])

    # Onboarding — orange, sans suivi de KPI (démo du toggle KPI)
    obj(onboarding, "Atteindre 70% de complétion", "amber", 2)
    jal(onboarding, 1, "Nouveau formulaire KYC", "done"); jal(onboarding, 2, "Optimisation écran 1", "in_progress")
    prog(onboarding, 100, 60, 0, 0)
    onboarding.kpis_enabled = False
    members(onboarding, [("Tom Bernard", "Squad leader", leaders["onboarding"].id), ("Julie Lopez", "Product", None)])

    # Support — rouge (jalon Q2 en retard)
    obj(support, "Réduire le temps de première réponse", "amber")
    jal(support, 1, "Base de connaissance interne", "done"); jal(support, 2, "Base publique", "late")
    prog(support, 100, 45, 0, 0)
    kpi(support, "Temps de première réponse", "under_pressure", 5.5, 4, "h")
    members(support, [("Lina Faure", "Squad leader", leaders["support"].id), ("Sofiane Atallah", "Support lead", None)])

    # Data Platform — tenu, périmé
    obj(dataplat, "Fiabiliser les pipelines temps réel", "green")
    jal(dataplat, 1, "Refonte orchestrateur", "done"); jal(dataplat, 2, "Monitoring qualité", "in_progress")
    prog(dataplat, 100, 65, 0, 0)
    kpi(dataplat, "Fraîcheur pipelines", "on_target", 1.5, 2, "h")
    members(dataplat, [("Yanis Petit", "Squad leader", leaders["dataplat"].id), ("Chloé Mercier", "Data engineer", None)])

    # Analytics — orange (jalon Q2 à risque)
    obj(analytics, "Livrer le datamart finance", "amber")
    jal(analytics, 1, "Modèle de données", "done"); jal(analytics, 2, "Datamart finance v1", "at_risk")
    prog(analytics, 100, 40, 0, 0)
    kpi(analytics, "Adoption des dashboards", "under_pressure", 45, 70, "%")
    members(analytics, [("Emma Girard", "Squad leader", leaders["analytics"].id), ("Adam Schmitt", "Analyste", None)])

    # Sécurité — orange (objectif amber)
    obj(secu, "Fermer les vulnérabilités critiques", "amber", 2)
    jal(secu, 1, "Scan automatisé", "done"); jal(secu, 2, "Correctifs critiques", "in_progress")
    jal(secu, 2, "Campagne de pentest", "at_risk")
    prog(secu, 100, 60, 10, 0)
    kpi(secu, "Vulnérabilités critiques ouvertes", "under_pressure", 4, 0, "")
    members(secu, [("Paul Lemoine", "Squad leader", leaders["secu"].id), ("Rania Haddad", "Pentester", None)])

    db.flush()

    # Demo of optional member hierarchy (the 3rd member reports to the 2nd).
    for sq in (aws, gcp, paiements):
        ms = sorted(sq.members, key=lambda m: m.display_order)
        if len(ms) >= 3:
            ms[2].manager_id = ms[1].id
    db.flush()

    # ---- Org chart per tribe: Direction -> domain entities -> squads (hybrid) ----
    def build_org(tribe, leader_name, domains):
        root = OrgNode(tribe_id=tribe.id, parent_id=None, title="Direction de la tribu",
                       person_name=leader_name, display_order=0)
        db.add(root)
        db.flush()
        for di, (dname, sqs) in enumerate(domains):
            entity = OrgNode(tribe_id=tribe.id, parent_id=root.id, title=dname, display_order=di)
            db.add(entity)
            db.flush()
            for i, s in enumerate(sqs):
                db.add(OrgNode(tribe_id=tribe.id, parent_id=entity.id, title=s.name,
                               person_name=s.leader.display_name if s.leader else None,
                               squad_id=s.id, display_order=i))

    build_org(tribe_a, "Nadia Khaldi", [
        ("Domaine Cloud", [aws, gcp, azure]),
        ("Domaine Sécurité & Paiements", [secu, paiements]),
    ])
    build_org(tribe_b, "Karim Belkacem", [
        ("Domaine Produit", [onboarding, support]),
        ("Domaine Data", [dataplat, analytics]),
    ])

    # ---- Snapshots / freshness. Azure and Data Platform are stale. ----
    threshold = settings.staleness_threshold_days
    fresh_days = {
        aws.id: 1, gcp.id: 1, azure.id: threshold + 5, paiements.id: 2,
        onboarding.id: 1, support.id: 3, dataplat.id: threshold + 8,
        analytics.id: 2, secu.id: 4,
    }
    by_id = {s.id: s for s in all_squads}
    for sid, days_ago in fresh_days.items():
        s = by_id[sid]
        for label, delta in (("Soumission précédente", days_ago + 21), ("Dernière soumission", days_ago)):
            db.add(ReportSnapshot(squad_id=sid, submitted_by_user_id=s.leader_user_id,
                                  submitted_at=now - timedelta(days=delta),
                                  payload=build_payload(s, year), cycle_label=label))

    # ---- Tweet zone (fil live) ----
    from .models import FeedPost, FeedReply, FeedReaction, Notification

    p1 = FeedPost(tribe_id=tribe_a.id, author_user_id=leaders["gcp"].id, kind="incident", squad_id=gcp.id, is_pinned=True,
                  content="Incident en cours sur le pipeline d'ingestion GCP : ingestion en pause, investigation lancée.",
                  created_at=now - timedelta(hours=3))
    p2 = FeedPost(tribe_id=None, author_user_id=marie.id, kind="info",
                  content="Annonce globale : revue trimestrielle de toute l'organisation vendredi 14h.",
                  created_at=now - timedelta(hours=8))
    p3 = FeedPost(tribe_id=tribe_a.id, author_user_id=leaders["aws"].id, kind="success", squad_id=aws.id,
                  content="Migration FinOps terminée : -12% sur la facture AWS ce trimestre.",
                  created_at=now - timedelta(days=1))
    p4 = FeedPost(tribe_id=tribe_b.id, author_user_id=leaders["analytics"].id, kind="info", squad_id=analytics.id,
                  content="Le datamart finance entre en recette la semaine prochaine.",
                  created_at=now - timedelta(hours=5))
    db.add_all([p1, p2, p3, p4])
    db.flush()
    db.add(FeedReply(post_id=p1.id, author_user_id=nadia.id, content="Merci, tenez-moi au courant de l'ETA de résolution.",
                     created_at=now - timedelta(hours=2)))
    db.add(FeedReply(post_id=p1.id, author_user_id=leaders["gcp"].id, content="ETA estimée en fin de journée.",
                     created_at=now - timedelta(hours=1)))
    db.add(FeedReaction(post_id=p3.id, user_id=nadia.id, kind="like"))
    db.add(FeedReaction(post_id=p3.id, user_id=marie.id, kind="like"))
    db.add(FeedReaction(post_id=p1.id, user_id=marie.id, kind="ack"))

    # ---- Demo notifications (unread) for the member persona (tribe A) ----
    db.add(Notification(user_id=hugo.id, kind="tweet", actor_name="Sara Dubois",
                        excerpt="Incident en cours sur le pipeline d'ingestion GCP…", link="/fil",
                        is_read=False, created_at=now - timedelta(hours=3)))
    db.add(Notification(user_id=hugo.id, kind="tweet", actor_name="Léo Martin",
                        excerpt="Migration FinOps terminée : -12% sur la facture AWS ce trimestre.", link="/fil",
                        is_read=False, created_at=now - timedelta(days=1)))

    db.commit()
    logger.info("Seed appliqué : %d squads (année %d), organigramme, fil live, comptes démo (mot de passe 'demo').",
                len(all_squads), year)
