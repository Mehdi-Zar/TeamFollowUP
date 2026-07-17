"""Review actions (COPIL decisions/actions per squad).

CRUD for the action items produced during a squad's review/COPIL meeting. Listing
is open to anyone who can see the squad (tribe scope); creating/updating/deleting
requires the "writer" role plus edit rights on the squad. The whole router is gated
by the `review` module toggle.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import (assert_can_edit_squad, assert_tribe_scope, get_current_user,
                    record_audit, require_module, require_writer)
from ..models import ReviewAction, Squad, User
from ..schemas import ReviewActionCreate, ReviewActionOut, ReviewActionUpdate

# Part of the review/COPIL feature - gated by the review module.
router = APIRouter(prefix="/api", tags=["actions"],
                   dependencies=[Depends(require_module("review"))])


@router.get("/squads/{squad_id}/actions", response_model=list[ReviewActionOut])
def list_actions(squad_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """List a squad's review actions.

    GET /api/squads/{squad_id}/actions
    Access: anyone within the squad's tribe scope (assert_tribe_scope).
    Ordering: open items first, then by due date (nulls last), then id.
    """
    squad = db.get(Squad, squad_id)
    if squad is None:
        raise HTTPException(status_code=404, detail="Squad introuvable")
    assert_tribe_scope(user, squad.tribe_id)  # anyone who can see the squad
    return db.scalars(
        select(ReviewAction).where(ReviewAction.squad_id == squad_id)
        .order_by(ReviewAction.done, ReviewAction.due_date.is_(None), ReviewAction.due_date, ReviewAction.id)
    ).all()


@router.post("/squads/{squad_id}/actions", response_model=ReviewActionOut, status_code=201)
def create_action(squad_id: int, payload: ReviewActionCreate, db: Session = Depends(get_db),
                  user: User = Depends(require_writer)):
    """Create a review action on a squad.

    POST /api/squads/{squad_id}/actions
    Access: writer role + edit rights on the squad (assert_can_edit_squad).
    Side effects: records the creator and writes a "review_action.create" audit entry.
    """
    if db.get(Squad, squad_id) is None:
        raise HTTPException(status_code=404, detail="Squad introuvable")
    assert_can_edit_squad(db, user, squad_id)
    action = ReviewAction(squad_id=squad_id, text=payload.text, owner=payload.owner,
                          due_date=payload.due_date, created_by_user_id=user.id)
    db.add(action)
    db.flush()
    record_audit(db, user.id, "review_action.create", entity="review_action", entity_id=action.id)
    db.commit()
    db.refresh(action)
    return action


@router.put("/actions/{action_id}", response_model=ReviewActionOut)
def update_action(action_id: int, payload: ReviewActionUpdate, db: Session = Depends(get_db),
                  user: User = Depends(require_writer)):
    """Partially update a review action (e.g. mark it done, change owner/due date).

    PUT /api/actions/{action_id}
    Access: writer role + edit rights on the action's squad.
    Only fields present in the payload are applied (exclude_unset). 404 if unknown.
    """
    action = db.get(ReviewAction, action_id)
    if action is None:
        raise HTTPException(status_code=404, detail="Action introuvable")
    assert_can_edit_squad(db, user, action.squad_id)
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(action, k, v)
    db.commit()
    db.refresh(action)
    return action


@router.delete("/actions/{action_id}", status_code=204)
def delete_action(action_id: int, db: Session = Depends(get_db), user: User = Depends(require_writer)):
    """Delete a review action.

    DELETE /api/actions/{action_id} -> 204 No Content
    Access: writer role + edit rights on the action's squad. 404 if unknown.
    """
    action = db.get(ReviewAction, action_id)
    if action is None:
        raise HTTPException(status_code=404, detail="Action introuvable")
    assert_can_edit_squad(db, user, action.squad_id)
    db.delete(action)
    db.commit()
