"""One-shot: wipe demo/org content and load the real Cloud Foundations org
(squads + products + hardware) from Orga.pptx. Login accounts (users), settings
and audit log are preserved.

Run inside the app container (cwd /app):
    docker compose exec -T app python - < backend/scripts/seed_real_org.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import update

from app.database import SessionLocal
from app.models import (
    FeedReaction, FeedReply, FeedPost, Notification, ReviewAction, ReportSubscription,
    OrgNode, ReportSnapshot, ProgressUpdate, KeyMessage, SquadBudget, Kpi,
    QuarterProgress, RoadmapItem, Objective, Initiative, Otd, Member, Squad, Tribe, User,
)

# Real org from Orga.pptx (Cloud Foundations Tribe). (name, type, products, hardware)
SQUADS = [
    ("Portal", "product", ["Post-it (ServiceNow)", "Custom Dev", "Backstage"], []),
    ("Managed Services", "product",
     ["SW/Sys/HW factories", "Kubernetes - Databases", "Vault - Observability"], ["DELL VxRAIL"]),
    ("TDP", "product", ["Azure"], []),
    ("TP-S3NS / TP-GCP", "product", ["GCP", "S3NS"], []),
    ("TP-AWS", "product", ["AWS"], []),
    ("CASTLE", "product", ["VMware VCF"], ["DELL VxRAIL"]),
    ("Edge Computing", "product", ["Morpheus", "OneEdge", "DAP"], []),
    ("Demand & Product Mgmt", "transverse", [], []),
    ("Architecture", "transverse", [], []),
    ("Run & Operations", "transverse", [], []),
    ("Customer Success", "transverse", [], []),
]

# Children → parents. Users / AppSetting / AuditLog are kept.
WIPE_ORDER = [
    FeedReaction, FeedReply, Notification, FeedPost, ReviewAction, ReportSubscription,
    OrgNode, ReportSnapshot, ProgressUpdate, KeyMessage, SquadBudget, Kpi,
    QuarterProgress, RoadmapItem, Objective, Initiative, Otd, Member, Squad, Tribe,
]


def main():
    db = SessionLocal()
    try:
        print("Wiping org content…")
        # Login accounts are kept, but they reference tribes (users.tribe_id) - detach
        # them first so the tribes can be deleted. Leaders can be reassigned afterwards.
        detached = db.execute(update(User).values(tribe_id=None)).rowcount
        print(f"  - users.tribe_id detached on {detached} accounts (kept)")
        for model in WIPE_ORDER:
            n = db.query(model).delete(synchronize_session=False)
            print(f"  - {model.__tablename__:20} {n} rows")
        db.commit()

        tribe = Tribe(name="Cloud Foundations Tribe", description="Cloud & Edge Computing", display_order=1)
        db.add(tribe)
        db.flush()
        for i, (name, typ, products, hardware) in enumerate(SQUADS, start=1):
            db.add(Squad(name=name, tribe_id=tribe.id, squad_type=typ,
                         products=products, hardware=hardware, display_order=i))
        db.commit()
        print(f"\nCreated tribe '{tribe.name}' with {len(SQUADS)} squads.")
        for s in db.query(Squad).order_by(Squad.display_order).all():
            print(f"  · {s.name:24} [{s.squad_type}] products={s.products} hardware={s.hardware}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
