"""Keep only the admin + one impersonation account per role (tribe_leader,
squad_leader, member); delete every other (fake) user. The 3 personas are scoped
to the real tribe, and the squad leader is made to lead one squad so that
"Manage my squads" has content.

Run inside the app container (cwd /app):
    docker compose exec -T app python - < backend/scripts/prune_users.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import update

from app.database import SessionLocal
from app.models import AuditLog, Squad, Tribe, User

KEEP_EMAILS = ["admin@local", "thomas.tl@local", "membre1@local", "camille.portal@local"]


def main():
    db = SessionLocal()
    try:
        tribe = db.query(Tribe).order_by(Tribe.id).first()
        tid = tribe.id if tribe else None
        keep = db.query(User).filter(User.email.in_(KEEP_EMAILS)).all()
        keep_ids = {u.id for u in keep}
        for u in keep:
            if not u.is_break_glass:          # scope the 3 demo personas to the real tribe
                u.tribe_id = tid

        sl = next((u for u in keep if u.role == "squad_leader"), None)
        portal = db.query(Squad).filter(Squad.name == "Portal").first()
        if sl and portal:
            portal.leader_user_id = sl.id

        others = db.query(User).filter(~User.id.in_(keep_ids)).all()
        oids = [u.id for u in others]
        if oids:
            db.execute(update(AuditLog).where(AuditLog.user_id.in_(oids)).values(user_id=None))
            db.execute(update(Squad).where(Squad.leader_user_id.in_(oids)).values(leader_user_id=None))
            for u in others:
                db.delete(u)
        db.commit()

        print(f"Deleted {len(oids)} fake users. Remaining accounts:")
        for u in db.query(User).order_by(User.id).all():
            print(f"  · #{u.id} {u.email:22} {u.role:13} tribe={u.tribe_id} break_glass={u.is_break_glass}")
        if sl and portal:
            print(f"\nSquad leader {sl.email} now leads '{portal.name}'.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
