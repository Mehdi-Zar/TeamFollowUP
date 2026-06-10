"""Idempotent demo seed — rich, fully-populated dataset to exercise every feature:
9 squads across 2 tribes, annual objectives (with target dates), a quarterly
roadmap with fully-filled milestones, quarter progress + comments, KPIs with
values/targets/comments, squad members (with manager hierarchy), an editable org
chart, report snapshots (two squads intentionally stale), a live feed with
replies/reactions, notifications, and a multi-week progress-review timeline
(weekly + review points, notes, confidence, deltas).
"""
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import status as st
from .config import settings
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

    def qdate(q: int, day: int = 15) -> datetime:
        """A target date in the middle month of quarter q."""
        return datetime(year, (q - 1) * 3 + 2, day, tzinfo=timezone.utc)

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
    hugo = mk_user("hugo.member@local", "Hugo Renaud", "member", tribe_a)
    db.flush()

    order = [0]

    def squad(name, lead_key, desc, tribe):
        order[0] += 1
        s = Squad(name=name, description=desc, leader_user_id=leaders[lead_key].id,
                  display_order=order[0], tribe_id=tribe.id)
        db.add(s)
        return s

    aws = squad("AWS", "aws", "Plateforme et services AWS : FinOps, résilience et industrialisation.", tribe_a)
    gcp = squad("GCP", "gcp", "Plateforme et services Google Cloud : data lake et ingestion temps réel.", tribe_a)
    azure = squad("Azure", "azure", "Plateforme et services Microsoft Azure : identités et sécurité.", tribe_a)
    paiements = squad("Paiements", "paiements", "Encaissement, réconciliation et résilience des paiements.", tribe_a)
    secu = squad("Sécurité", "secu", "Sécurité applicative, conformité et gestion des vulnérabilités.", tribe_a)
    onboarding = squad("Onboarding", "onboarding", "Parcours d'entrée client : KYC et activation.", tribe_b)
    support = squad("Support produit", "support", "Relation et succès client : self-care et délais de réponse.", tribe_b)
    dataplat = squad("Data Platform", "dataplat", "Pipelines, orchestration et qualité du socle data.", tribe_b)
    analytics = squad("Analytics", "analytics", "Reporting, datamarts et adoption du décisionnel.", tribe_b)
    db.flush()

    all_squads = [aws, gcp, azure, paiements, onboarding, support, dataplat, analytics, secu]

    def obj(s, title, rag, w=1, desc=None, q=None):
        db.add(Objective(squad_id=s.id, year=year, title=title, rag_status=rag, weight=w,
                         description=desc, target_date=qdate(q) if q else None))

    _jmap = {"planned": "on_track", "in_progress": "on_track", "done": "done", "at_risk": "at_risk", "late": "blocked"}

    def jal(s, q, title, status, o=0, owner=None, benefit=None, desc=None, success=None, deps=None, risks=None):
        db.add(RoadmapItem(squad_id=s.id, year=year, quarter=q, title=title,
                           status=_jmap.get(status, status), display_order=o,
                           owner=owner, user_benefit=benefit, description=desc,
                           success_criteria=success, dependencies=deps, risks=risks))

    def prog(s, vals, comments=(None, None, None, None)):
        for q, v, c in zip((1, 2, 3, 4), vals, comments):
            db.add(QuarterProgress(squad_id=s.id, year=year, quarter=q, progress_pct=v, comment=c))

    def kpi(s, name, trend, cur=None, tgt=None, unit=None, comment=None):
        db.add(Kpi(squad_id=s.id, name=name, trend_status=trend, current_value=cur,
                   target_value=tgt, unit=unit, comment=comment))

    def members(s, people):
        for i, (name, role_title, user_id) in enumerate(people):
            db.add(Member(squad_id=s.id, full_name=name, role_title=role_title, user_id=user_id, display_order=i))

    # ============================ AWS — sain ============================
    obj(aws, "Optimiser le coût de la facture AWS", "green", 2,
        desc="Réduire de 15% la facture mensuelle via FinOps et instances réservées.", q=2)
    obj(aws, "Migrer 80% des charges vers du managé", "green", 1,
        desc="Basculer les services auto-gérés vers des offres managées (RDS, EKS).", q=4)
    jal(aws, 1, "Audit FinOps", "done", 0, owner="Hugo Renaud",
        desc="Cartographie complète des coûts AWS par squad et par environnement.",
        success="Rapport FinOps validé et plan d'économies chiffré.",
        benefit="Visibilité claire des postes de coût et des gisements d'économie.",
        deps="Accès facturation consolidée (compte payeur).",
        risks="Données de facturation incomplètes sur les comptes legacy.")
    jal(aws, 2, "Instances réservées", "done", 0, owner="Camille Roux",
        desc="Souscription d'instances réservées sur les charges stables identifiées.",
        success="-20% sur les coûts de calcul stables.",
        benefit="Économies récurrentes sans impact sur la disponibilité.",
        deps="Validation budgétaire de la Direction.",
        risks="Sur-engagement si la charge baisse.")
    jal(aws, 2, "Tagging des ressources", "in_progress", 1, owner="Hugo Renaud",
        desc="Standardiser le tagging de toutes les ressources AWS (équipe, environnement, coût).",
        success="100% des ressources taguées et conformes à la politique FinOps.",
        benefit="Refacturation précise par squad et meilleure visibilité des coûts.",
        deps="Politique de tagging validée par la Sécurité.",
        risks="Ressources legacy difficiles à taguer sans interruption de service.")
    jal(aws, 3, "Auto-scaling avancé", "planned", 0, owner="Camille Roux",
        desc="Mettre en place l'auto-scaling prédictif sur les charges variables.",
        success="Réduction de 25% de la sur-capacité aux heures creuses.",
        benefit="Coûts alignés sur l'usage réel.",
        deps="Métriques de charge historisées sur 6 mois.",
        risks="Réactivité insuffisante en cas de pic soudain.")
    jal(aws, 4, "Bilan FinOps annuel", "planned", 0, owner="Léo Martin",
        desc="Consolidation des économies et plan pour l'année suivante.")
    prog(aws, (100, 70, 10, 0),
         ("Audit livré, base FinOps posée.", "Tagging en cours, RI souscrites.",
          "Démarrage auto-scaling prévu après le tagging.", None))
    kpi(aws, "Disponibilité", "on_target", 99.98, 99.9, "%", comment="SLA tenu sur tout le trimestre.")
    kpi(aws, "Économies réalisées", "on_target", 12, 15, "%", comment="En bonne voie vers la cible annuelle.")
    members(aws, [("Léo Martin", "Squad leader", leaders["aws"].id),
                  ("Hugo Renaud", "Ingénieur cloud", hugo.id), ("Camille Roux", "SRE", None)])

    # ============================ GCP — rouge ============================
    obj(gcp, "Mettre en place le data lake GCP", "amber", 2,
        desc="Socle d'ingestion temps réel vers BigQuery pour le décisionnel.", q=2)
    obj(gcp, "Industrialiser l'IaC GCP", "red", 1,
        desc="Tout le provisioning via Terraform, revue de sécurité incluse.", q=3)
    jal(gcp, 1, "POC BigQuery", "done", 0, owner="Noah Blanc",
        desc="Validation technique de BigQuery comme entrepôt cible.",
        success="POC concluant sur un jeu de données représentatif.",
        benefit="Choix d'architecture sécurisé pour la suite.",
        deps="Jeu de données de test anonymisé.",
        risks="Volumétrie réelle plus élevée que le POC.")
    jal(gcp, 2, "Pipeline d'ingestion", "late", 0, owner="Noah Blanc",
        desc="Pipeline d'ingestion temps réel des événements vers BigQuery.",
        success="Ingestion < 4h de bout en bout, 99% de complétude.",
        benefit="Données fraîches pour le reporting décisionnel.",
        deps="Ouverture réseau vers l'amont (équipe Infra) — bloquée.",
        risks="Dépendance réseau non résolue : tout le quarter est à l'arrêt.")
    jal(gcp, 2, "IAM et cloisonnement", "at_risk", 1, owner="Sara Dubois",
        desc="Cloisonnement des accès par projet GCP.",
        success="Séparation stricte des environnements, moindre privilège.",
        benefit="Réduction de la surface d'attaque.",
        deps="Modèle d'habilitation validé par la Sécurité.",
        risks="Modèle d'habilitation pas encore validé par la Sécurité.")
    jal(gcp, 3, "Mise en production", "planned", 0, owner="Sara Dubois",
        desc="Bascule du data lake en production avec supervision.",
        success="Run stabilisé, alerting en place.",
        deps="Pipeline d'ingestion débloqué.",
        risks="Retard cumulé du Q2.")
    prog(gcp, (90, 30, 0, 0),
         ("POC réussi.", "Pipeline bloqué par une dépendance réseau Infra.", None, None))
    kpi(gcp, "Latence d'ingestion", "missed", 12, 4, "h", comment="Bloquée par la dépendance réseau.")
    kpi(gcp, "Complétude des données", "under_pressure", 92, 99, "%", comment="Lacunes sur les sources amont.")
    members(gcp, [("Sara Dubois", "Squad leader", leaders["gcp"].id),
                  ("Noah Blanc", "Data engineer", None), ("Yuki Tanaka", "Data engineer", None)])

    # ============================ Azure — sain, périmé ============================
    obj(azure, "Sécuriser les identités (Entra ID)", "green", 2,
        desc="MFA généralisé et SSO sur toutes les applications internes.", q=2)
    jal(azure, 1, "Connecteur SSO", "done", 0, owner="Inès Marchand",
        desc="SSO Entra ID sur le portail interne.",
        success="100% des apps internes derrière le SSO.",
        benefit="Moins de mots de passe, meilleure traçabilité.")
    jal(azure, 2, "MFA généralisé", "in_progress", 0, owner="Kevin Roy",
        desc="Déploiement du MFA pour tous les collaborateurs.",
        success="Couverture MFA > 95%.",
        benefit="Réduction drastique du risque de compromission.",
        deps="Campagne de communication RH.",
        risks="Résistance au changement sur certaines équipes.")
    jal(azure, 3, "Revue des accès privilégiés", "planned", 0, owner="Kevin Roy",
        desc="Revue trimestrielle des comptes à privilèges.")
    prog(azure, (100, 50, 0, 0),
         ("SSO livré.", "MFA en cours de déploiement.", None, None))
    kpi(azure, "Couverture MFA", "on_target", 88, 80, "%", comment="Au-dessus de la cible intermédiaire.")
    members(azure, [("Kevin Roy", "Squad leader", leaders["azure"].id),
                    ("Inès Marchand", "Ingénieure cloud", None)])

    # ============================ Paiements — rouge ============================
    obj(paiements, "Réduire le taux d'échec sous 1%", "red", 3,
        desc="Fiabiliser la chaîne d'autorisation pour passer sous 1% d'échec.", q=2)
    obj(paiements, "Migrer vers le nouveau PSP", "amber", 2,
        desc="Bascule complète du trafic vers le PSP v2.", q=3)
    jal(paiements, 1, "Connecteur PSP v2", "done", 0, owner="Marc Olivier",
        desc="Intégration technique du nouveau prestataire de paiement.",
        success="Connecteur certifié et testé en pré-production.",
        benefit="Base pour réduire coûts et taux d'échec.",
        deps="Accès sandbox PSP.",
        risks="Spécifications PSP incomplètes.")
    jal(paiements, 2, "Bascule progressive", "at_risk", 0, owner="Ana Costa",
        desc="Bascule progressive du trafic vers le nouveau PSP (10% → 100%).",
        success="100% du trafic basculé sans hausse du taux d'échec.",
        benefit="Réduction des coûts de transaction et meilleure résilience.",
        deps="Validation conformité PCI-DSS.",
        risks="Incident PSP récurrent qui freine la montée en charge.")
    jal(paiements, 3, "Réconciliation automatisée", "planned", 0, owner="Marc Olivier",
        desc="Automatiser la réconciliation comptable des paiements.",
        success="Réconciliation quotidienne sans intervention manuelle.")
    prog(paiements, (100, 55, 5, 0),
         ("Connecteur v2 livré.", "Bascule freinée par des incidents PSP.", None, None))
    kpi(paiements, "Taux d'échec paiement", "missed", 1.8, 1.0, "%", comment="Au-dessus de la cible critique.")
    kpi(paiements, "Latence autorisation", "under_pressure", 420, 300, "ms", comment="Pics pendant la bascule.")
    members(paiements, [("Ana Costa", "Squad leader", leaders["paiements"].id),
                        ("Marc Olivier", "Backend", None), ("Sophie Nguyen", "QA", None)])

    # ============================ Onboarding — orange, sans KPI ============================
    obj(onboarding, "Atteindre 70% de complétion KYC", "amber", 2,
        desc="Optimiser le parcours pour augmenter le taux de complétion.", q=2)
    jal(onboarding, 1, "Nouveau formulaire KYC", "done", 0, owner="Julie Lopez",
        desc="Refonte du formulaire KYC pour réduire la friction.",
        success="Temps de complétion divisé par deux.",
        benefit="Plus de clients activés.")
    jal(onboarding, 2, "Optimisation écran 1", "in_progress", 0, owner="Tom Bernard",
        desc="Simplifier la première étape, source principale d'abandon.",
        success="Taux d'abandon écran 1 < 15%.",
        benefit="Moins d'abandons en haut du tunnel.",
        risks="Contraintes réglementaires sur les champs obligatoires.")
    prog(onboarding, (100, 60, 0, 0),
         ("Formulaire KYC livré.", "Optimisation écran 1 en cours.", None, None))
    onboarding.kpis_enabled = False
    members(onboarding, [("Tom Bernard", "Squad leader", leaders["onboarding"].id),
                         ("Julie Lopez", "Product", None)])

    # ============================ Support — rouge ============================
    obj(support, "Réduire le temps de première réponse", "amber", 2,
        desc="Passer sous 4h de délai de première réponse.", q=2)
    jal(support, 1, "Base de connaissance interne", "done", 0, owner="Sofiane Atallah",
        desc="Centraliser les réponses types pour les agents.",
        success="80% des demandes couvertes par un article.",
        benefit="Réponses plus rapides et homogènes.")
    jal(support, 2, "Base de connaissance publique", "late", 0, owner="Lina Faure",
        desc="Self-care client : portail d'aide public.",
        success="-20% de tickets entrants sur les sujets couverts.",
        benefit="Déflexion des demandes simples.",
        deps="Validation juridique des contenus publics.",
        risks="Validation juridique en retard, sujet bloqué.")
    prog(support, (100, 45, 0, 0),
         ("Base interne livrée.", "Base publique bloquée côté juridique.", None, None))
    kpi(support, "Temps de première réponse", "under_pressure", 5.5, 4, "h", comment="Au-dessus de la cible.")
    kpi(support, "Satisfaction (CSAT)", "on_target", 4.3, 4.0, "/5", comment="Bon niveau de satisfaction.")
    members(support, [("Lina Faure", "Squad leader", leaders["support"].id),
                      ("Sofiane Atallah", "Support lead", None)])

    # ============================ Data Platform — sain, périmé ============================
    obj(dataplat, "Fiabiliser les pipelines temps réel", "green", 2,
        desc="Refondre l'orchestration et la supervision qualité.", q=2)
    jal(dataplat, 1, "Refonte orchestrateur", "done", 0, owner="Chloé Mercier",
        desc="Migration vers un orchestrateur moderne (Airflow managé).",
        success="Tous les jobs migrés, zéro régression.",
        benefit="Pipelines plus robustes et observables.")
    jal(dataplat, 2, "Monitoring qualité", "in_progress", 0, owner="Yanis Petit",
        desc="Contrôles qualité automatisés sur les pipelines critiques.",
        success="Alerting sur fraîcheur et complétude.",
        benefit="Détection précoce des anomalies de données.",
        deps="Catalogue des jeux de données critiques.")
    prog(dataplat, (100, 65, 0, 0),
         ("Orchestrateur refondu.", "Monitoring qualité en cours.", None, None))
    kpi(dataplat, "Fraîcheur pipelines", "on_target", 1.5, 2, "h", comment="Sous la cible, bon niveau.")
    members(dataplat, [("Yanis Petit", "Squad leader", leaders["dataplat"].id),
                       ("Chloé Mercier", "Data engineer", None)])

    # ============================ Analytics — orange ============================
    obj(analytics, "Livrer le datamart finance", "amber", 2,
        desc="Datamart finance v1 et adoption par les équipes métier.", q=2)
    jal(analytics, 1, "Modèle de données", "done", 0, owner="Adam Schmitt",
        desc="Modélisation dimensionnelle du domaine finance.",
        success="Modèle validé par les métiers finance.",
        benefit="Base commune et fiable pour le reporting.")
    jal(analytics, 2, "Datamart finance v1", "at_risk", 0, owner="Emma Girard",
        desc="Construction et exposition du datamart finance.",
        success="Dashboards finance branchés sur le datamart.",
        benefit="Reporting finance fiable et self-service.",
        deps="Données sources consolidées par Data Platform.",
        risks="Qualité des sources amont insuffisante.")
    prog(analytics, (100, 40, 0, 0),
         ("Modèle de données validé.", "Datamart à risque sur la qualité des sources.", None, None))
    kpi(analytics, "Adoption des dashboards", "under_pressure", 45, 70, "%", comment="Adoption à stimuler.")
    members(analytics, [("Emma Girard", "Squad leader", leaders["analytics"].id),
                        ("Adam Schmitt", "Analyste", None)])

    # ============================ Sécurité — orange ============================
    obj(secu, "Fermer les vulnérabilités critiques", "amber", 2,
        desc="Aucune vulnérabilité critique ouverte en fin de trimestre.", q=2)
    obj(secu, "Industrialiser le pentest", "amber", 1,
        desc="Campagnes de pentest régulières et suivi des correctifs.", q=3)
    jal(secu, 1, "Scan automatisé", "done", 0, owner="Rania Haddad",
        desc="Scan de vulnérabilités intégré à la CI/CD.",
        success="Scan systématique à chaque déploiement.",
        benefit="Détection précoce des vulnérabilités.")
    jal(secu, 2, "Correctifs critiques", "in_progress", 0, owner="Paul Lemoine",
        desc="Traitement des vulnérabilités critiques ouvertes.",
        success="0 vulnérabilité critique ouverte.",
        benefit="Réduction du risque de sécurité.",
        risks="Certains correctifs nécessitent des fenêtres de maintenance.")
    jal(secu, 2, "Campagne de pentest", "at_risk", 1, owner="Rania Haddad",
        desc="Pentest applicatif externe sur le périmètre critique.",
        success="Rapport de pentest et plan de remédiation.",
        deps="Disponibilité du prestataire externe.",
        risks="Créneau prestataire repoussé.")
    prog(secu, (100, 60, 10, 0),
         ("Scan automatisé en place.", "Correctifs en cours, pentest à planifier.", None, None))
    kpi(secu, "Vulnérabilités critiques ouvertes", "under_pressure", 4, 0, "", comment="4 critiques restantes.")
    members(secu, [("Paul Lemoine", "Squad leader", leaders["secu"].id),
                   ("Rania Haddad", "Pentester", None)])

    db.flush()

    # Member hierarchy demo (3rd member reports to the 2nd).
    for sq in (aws, gcp, paiements):
        ms = sorted(sq.members, key=lambda m: m.display_order)
        if len(ms) >= 3:
            ms[2].manager_id = ms[1].id
    db.flush()

    # ---- Org chart per tribe ----
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

    # ---- Snapshots / freshness (Azure and Data Platform intentionally stale) ----
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

    # ---- Progress-review timeline (weekly + review points, deltas, confidence) ----
    seed_progress(db, all_squads, year, now)

    # ---- Tweet zone (fil live) ----
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
    p5 = FeedPost(tribe_id=tribe_a.id, author_user_id=leaders["paiements"].id, kind="incident", squad_id=paiements.id,
                  content="Taux d'échec paiement au-dessus de la cible pendant la bascule PSP : suivi rapproché.",
                  created_at=now - timedelta(hours=20))
    db.add_all([p1, p2, p3, p4, p5])
    db.flush()
    db.add(FeedReply(post_id=p1.id, author_user_id=nadia.id, content="Merci, tenez-moi au courant de l'ETA de résolution.",
                     created_at=now - timedelta(hours=2)))
    db.add(FeedReply(post_id=p1.id, author_user_id=leaders["gcp"].id, content="ETA estimée en fin de journée.",
                     created_at=now - timedelta(hours=1)))
    db.add(FeedReply(post_id=p3.id, author_user_id=marie.id, content="Bravo à l'équipe AWS !",
                     created_at=now - timedelta(hours=20)))
    db.add(FeedReaction(post_id=p3.id, user_id=nadia.id, kind="like"))
    db.add(FeedReaction(post_id=p3.id, user_id=marie.id, kind="like"))
    db.add(FeedReaction(post_id=p1.id, user_id=marie.id, kind="ack"))
    db.add(FeedReaction(post_id=p4.id, user_id=karim.id, kind="like"))

    # ---- Notifications (unread) for the member persona ----
    db.add(Notification(user_id=hugo.id, kind="tweet", actor_name="Sara Dubois",
                        excerpt="Incident en cours sur le pipeline d'ingestion GCP…", link="/fil",
                        is_read=False, created_at=now - timedelta(hours=3)))
    db.add(Notification(user_id=hugo.id, kind="tweet", actor_name="Léo Martin",
                        excerpt="Migration FinOps terminée : -12% sur la facture AWS ce trimestre.", link="/fil",
                        is_read=False, created_at=now - timedelta(days=1)))

    db.commit()
    logger.info("Seed appliqué : %d squads (année %d), objectifs datés, jalons détaillés, "
                "frise de progression, fil live. Mot de passe démo : 'demo'.", len(all_squads), year)


# Per-squad narrative for the progress timeline: confidence trend + review notes.
_PROGRESS_NARRATIVE = {
    "AWS": (4, [
        "Audit FinOps livré, base solide. Confiance haute sur la cible annuelle.",
        "RI souscrites, tagging bien avancé. On tient le rythme.",
    ]),
    "GCP": (2, [
        "Pipeline d'ingestion bloqué par une dépendance réseau Infra. Point d'attention fort.",
        "Toujours en attente de l'ouverture réseau. Escalade en cours auprès de l'Infra.",
    ]),
    "Azure": (4, [
        "SSO livré, déploiement MFA lancé. Tout est sous contrôle.",
        "Couverture MFA au-dessus de la cible intermédiaire.",
    ]),
    "Paiements": (2, [
        "Bascule PSP freinée par des incidents récurrents. Taux d'échec au-dessus de la cible.",
        "Stabilisation en cours avec le PSP, montée en charge prudente.",
    ]),
    "Onboarding": (3, [
        "Formulaire KYC refondu et livré. Optimisation écran 1 démarrée.",
    ]),
    "Support produit": (2, [
        "Base publique bloquée par la validation juridique. Délai de réponse encore au-dessus de la cible.",
    ]),
    "Data Platform": (4, [
        "Orchestrateur refondu sans régression. Monitoring qualité en cours.",
    ]),
    "Analytics": (3, [
        "Datamart finance à risque sur la qualité des sources amont. Adoption à stimuler.",
    ]),
    "Sécurité": (3, [
        "Scan automatisé en place. Reste 4 vulnérabilités critiques et le pentest à planifier.",
    ]),
}


def seed_progress(db: Session, squads: list[Squad], year: int, now: datetime) -> None:
    """Create a believable multi-week progress timeline for each squad."""
    n_points = 9  # ~2 months of weekly points
    for s in squads:
        metrics = compute_metrics(s, year)
        cur_pct = metrics["progress_pct"]
        total = metrics["total_count"]
        cur_blocked = metrics["blocked_count"]
        cur_at_risk = metrics["at_risk_count"]
        cur_done = metrics["done_count"]
        base_conf, notes = _PROGRESS_NARRATIVE.get(s.name, (3, []))

        prev_pct = 0
        for i in range(n_points):  # oldest -> newest
            frac = (i + 1) / n_points
            pct = round(cur_pct * frac)
            done = round(cur_done * frac)
            # Risks/blockers appear in the second half of the timeline.
            blocked = cur_blocked if i >= n_points - 3 else 0
            at_risk = cur_at_risk if i >= n_points - 5 else max(0, cur_at_risk - 1)
            created = now - timedelta(days=(n_points - 1 - i) * 7 + 1, hours=9)

            changes = []
            if pct != prev_pct:
                # attribute the bump to the most-advanced active quarter
                changes.append({"kind": "quarter_pct", "label": "Q2", "from": prev_pct, "to": pct})
            if blocked and i == n_points - 3:
                changes.append({"kind": "jalon_status", "label": "Jalon critique",
                                "from": "at_risk", "to": "blocked"})

            kind = "weekly"
            note = None
            confidence = None
            created_by = None
            # Turn a couple of points into explicit reviews with note + confidence.
            review_slots = {n_points - 1: 0, n_points - 4: 1}
            if i in review_slots and review_slots[i] < len(notes):
                kind = "review"
                note = notes[review_slots[i]]
                # confidence dips earlier, recovers (or not) at the latest point
                confidence = max(1, min(5, base_conf + (0 if i == n_points - 1 else -1)))
                created_by = s.leader_user_id

            db.add(ProgressUpdate(
                squad_id=s.id, year=year, created_at=created, created_by_user_id=created_by,
                kind=kind, note=note, confidence=confidence, progress_pct=pct,
                blocked_count=blocked, at_risk_count=at_risk, done_count=done,
                total_count=total, state=None, changes=changes,
            ))
            prev_pct = pct
