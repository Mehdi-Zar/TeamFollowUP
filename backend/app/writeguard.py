"""One check on every write: what the screens send fits the columns it goes into.

Pydantic schemas set a few bounds, not all of them, and SQLite (the tests) accepts
a 600-character title in a VARCHAR(500) where PostgreSQL (production) raises a
DataError, which surfaced as a 500 on a plain form. Checked here, on the objects
about to be written, whatever route wrote them:

  * a string longer than its column: 422, naming the field and the limit;
  * a naming field (title, name, text, theme...) made only of spaces: 422;
  * a ``year`` outside a plausible range: 422.

Registered once on the Session class (``install``), so every session gets it,
tests included.
"""
from fastapi import HTTPException
from sqlalchemy import String, event
from sqlalchemy.orm import Session

# Fields that name a row: blank (spaces only) is as missing as empty.
_NAMING = {"title", "name", "full_name", "display_name", "text", "theme"}
# How a field reads in the message (French, like the server's other messages).
_LABEL = {"title": "titre", "name": "nom", "full_name": "nom", "display_name": "nom",
          "text": "texte", "theme": "thème", "owner": "porteur", "unit": "unité",
          "comment": "commentaire", "description": "description", "role_title": "fonction",
          "cycle_label": "libellé", "email": "email"}
YEAR_MIN, YEAR_MAX = 2000, 2100


def _check(obj) -> None:
    table = getattr(obj, "__table__", None)
    if table is None:
        return
    for col in table.columns:
        key = col.key
        if not hasattr(obj, key):
            continue
        val = getattr(obj, key)
        label = _LABEL.get(key, key)
        if isinstance(val, str):
            length = getattr(col.type, "length", None) if isinstance(col.type, String) else None
            if length and len(val) > length:
                raise HTTPException(status_code=422,
                                    detail=f"Le champ « {label} » dépasse {length} caractères ({len(val)}).")
            if key in _NAMING and not col.nullable and not val.strip():
                raise HTTPException(status_code=422, detail=f"Le champ « {label} » ne peut pas être vide.")
        if key == "year" and isinstance(val, int) and not (YEAR_MIN <= val <= YEAR_MAX):
            raise HTTPException(status_code=422, detail=f"Année invalide : {val}.")


def _before_flush(session: Session, flush_context, instances) -> None:
    for obj in list(session.new) + list(session.dirty):
        _check(obj)


def install() -> None:
    """Attach the guard to every Session (idempotent)."""
    if not event.contains(Session, "before_flush", _before_flush):
        event.listen(Session, "before_flush", _before_flush)
