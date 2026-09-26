"""Answers for the errors no route handles itself.

Without these, a crash reached the screen as "Internal Server Error" (English,
no clue), a constraint failure as the same 500, and a validation error as
Pydantic's English sentence ("Input should be a valid integer"). Each case now
gets a readable message, in the language the client asks for (the SPA sends
``Accept-Language``: "fr" or "en").

- ``HTTPException``: the route's own status and headers; its French detail is
  sent in English when the client asks for it (catalog in ``errmsgs.py``).
- ``RequestValidationError``: 422, the same list shape as FastAPI's (``loc``,
  ``type``, ``msg``), ``msg`` rewritten as "<field>: <reason>".
- ``IntegrityError``: 409, the session rolled back (a reference to a missing row
  or a duplicate).
- ``DataError`` / ``OverflowError``: 422, a value outside what the column holds.
- anything else: 500 with a short reference, logged with the traceback under the
  same reference so a report from the screen can be found in the logs.
"""
import logging
import uuid

from fastapi import FastAPI, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DataError, IntegrityError
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import errmsgs

log = logging.getLogger("app.errors")

# Pydantic error type -> (fr, en). Anything else keeps a generic wording.
_REASONS = {
    "missing": ("champ obligatoire", "required field"),
    "string_type": ("texte attendu", "text expected"),
    "string_too_short": ("trop court", "too short"),
    "string_too_long": ("trop long ({max_length} caractères au plus)", "too long ({max_length} characters at most)"),
    "int_type": ("nombre entier attendu", "whole number expected"),
    "int_parsing": ("nombre entier attendu", "whole number expected"),
    "int_from_float": ("nombre entier attendu", "whole number expected"),
    "float_type": ("nombre attendu", "number expected"),
    "float_parsing": ("nombre attendu", "number expected"),
    "bool_type": ("oui ou non attendu", "yes or no expected"),
    "bool_parsing": ("oui ou non attendu", "yes or no expected"),
    "date_type": ("date attendue", "date expected"),
    "date_parsing": ("date attendue (AAAA-MM-JJ)", "date expected (YYYY-MM-DD)"),
    "date_from_datetime_parsing": ("date attendue (AAAA-MM-JJ)", "date expected (YYYY-MM-DD)"),
    "datetime_type": ("date et heure attendues", "date and time expected"),
    "datetime_parsing": ("date et heure attendues", "date and time expected"),
    "datetime_from_date_parsing": ("date et heure attendues", "date and time expected"),
    "greater_than": ("doit être supérieur à {gt}", "must be greater than {gt}"),
    "greater_than_equal": ("doit être au moins {ge}", "must be at least {ge}"),
    "less_than": ("doit être inférieur à {lt}", "must be less than {lt}"),
    "less_than_equal": ("doit être au plus {le}", "must be at most {le}"),
    "literal_error": ("valeur non permise (attendu : {expected})", "value not allowed (expected: {expected})"),
    "enum": ("valeur non permise (attendu : {expected})", "value not allowed (expected: {expected})"),
    "list_type": ("liste attendue", "list expected"),
    "dict_type": ("objet attendu", "object expected"),
    "model_attributes_type": ("objet attendu", "object expected"),
    "json_invalid": ("JSON invalide", "invalid JSON"),
    "value_error": ("{msg}", "{msg}"),
}
_GENERIC = ("valeur invalide", "invalid value")


def lang_of(request: Request) -> str:
    """"en" when the client asks for English first, else French (the default)."""
    return "en" if (request.headers.get("accept-language") or "").lower().startswith("en") else "fr"


def _reason(err: dict, en: bool) -> str:
    fr_txt, en_txt = _REASONS.get(err.get("type", ""), _GENERIC)
    ctx = dict(err.get("ctx") or {})
    # A validator's own message (ValueError) is already written for people.
    msg = str(err.get("msg") or "")
    ctx.setdefault("msg", msg.removeprefix("Value error, "))
    try:
        return (en_txt if en else fr_txt).format(**{k: v for k, v in ctx.items()})
    except (KeyError, IndexError, ValueError):
        return en_txt if en else fr_txt


def _field(loc) -> str:
    """The field named by the error: the last readable part of ``loc``."""
    parts = [str(p) for p in (loc or ()) if not isinstance(p, int) and p not in ("body", "query", "path")]
    return parts[-1] if parts else ""


def install(app: FastAPI) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException):
        # Routes raise their details in French; an English client reads them in
        # English (catalog in errmsgs.py). Status and headers are kept, and a
        # detail that is not text (codes, lists, objects) passes through.
        if isinstance(exc.detail, str) and lang_of(request) == "en":
            en = errmsgs.translate(exc.detail)
            if en != exc.detail:
                exc = StarletteHTTPException(exc.status_code, detail=en, headers=exc.headers)
        return await http_exception_handler(request, exc)

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError):
        en = lang_of(request) == "en"
        out = []
        for err in exc.errors():
            field = _field(err.get("loc"))
            reason = _reason(err, en)
            sep = ": " if en else " : "
            out.append({"loc": list(err.get("loc") or ()), "type": err.get("type"),
                        "msg": f"{field}{sep}{reason}" if field else reason})
        return JSONResponse(status_code=422, content={"detail": out})

    @app.exception_handler(IntegrityError)
    async def _integrity(request: Request, exc: IntegrityError):
        log.warning("integrity error on %s %s: %s", request.method, request.url.path, exc.orig)
        en = lang_of(request) == "en"
        return JSONResponse(status_code=409, content={"detail": (
            "Unknown reference or duplicate: check the chosen items and try again." if en else
            "Référence inconnue ou doublon : vérifiez les éléments choisis puis réessayez.")})

    async def _out_of_range(request: Request, exc: Exception):
        log.warning("out of range value on %s %s: %s", request.method, request.url.path, exc)
        en = lang_of(request) == "en"
        return JSONResponse(status_code=422, content={"detail": (
            "A value is out of range." if en else "Une valeur est hors limites.")})

    app.add_exception_handler(DataError, _out_of_range)
    app.add_exception_handler(OverflowError, _out_of_range)

    @app.exception_handler(Exception)
    async def _unexpected(request: Request, exc: Exception):
        ref = uuid.uuid4().hex[:8]
        log.exception("unexpected error [%s] on %s %s", ref, request.method, request.url.path)
        en = lang_of(request) == "en"
        return JSONResponse(status_code=500, content={"detail": (
            f"Unexpected error. Reference: {ref}" if en else f"Erreur inattendue. Référence : {ref}")})
