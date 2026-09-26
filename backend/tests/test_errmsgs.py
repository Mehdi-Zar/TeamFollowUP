"""HTTPException details in English when the client asks for it.

Routes raise their messages in French; ``errors.py`` translates them through
``app/errmsgs.py`` for ``Accept-Language: en``. The coverage tests below read
every ``HTTPException(detail=...)`` of ``app/`` so a new French message cannot
ship without its English wording.
"""
import ast
from pathlib import Path

from app import errmsgs
from tests.conftest import login

APP = Path(__file__).resolve().parents[1] / "app"
EN = {"Accept-Language": "en"}


def _details():
    """(where, node) for each detail given to an HTTPException in app/."""
    for path in sorted(APP.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
            if name != "HTTPException":
                continue
            vals = [k.value for k in node.keywords if k.arg == "detail"]
            if len(node.args) > 1:
                vals.append(node.args[1])
            for v in vals:
                yield f"{path.relative_to(APP)}:{node.lineno}", v


def _sample(node: ast.JoinedStr) -> str:
    """An f-string rendered with "12" for every value it inserts."""
    return "".join(p.value if isinstance(p, ast.Constant) else "12" for p in node.values)


def test_every_literal_detail_has_an_english_wording():
    missing = []
    for where, v in _details():
        if isinstance(v, ast.Constant) and isinstance(v.value, str):
            if v.value in ("access_pending", "access_disabled"):
                continue
            if errmsgs.translate(v.value) == v.value:
                missing.append(f"{where}: {v.value}")
    assert not missing, "No English wording in app/errmsgs.py for:\n" + "\n".join(missing)


def test_every_fstring_detail_matches_a_pattern():
    missing = []
    for where, v in _details():
        if isinstance(v, ast.JoinedStr):
            text = _sample(v)
            if errmsgs.translate(text) == text:
                missing.append(f"{where}: {text}")
    assert not missing, "No pattern in app/errmsgs.py for:\n" + "\n".join(missing)


def test_patterns_reuse_the_values():
    assert errmsgs.translate("Le champ « titre » dépasse 200 caractères (250).") == \
        'The "title" field is longer than 200 characters (250).'
    assert errmsgs.translate("Import impossible : bad cell B4") == "Import failed: bad cell B4"
    assert errmsgs.translate("Alice Martin n'appartient pas à la tribe de cette squad") == \
        "Alice Martin does not belong to this squad's tribe"
    assert errmsgs.translate("Texte inconnu") == "Texte inconnu"


def test_not_found_in_english(client, seeded):
    login(client, "admin@test")
    r = client.get("/api/squads/999999", headers=EN)
    assert r.status_code == 404
    assert r.json() == {"detail": "Squad not found"}


def test_not_found_stays_french_by_default(client, seeded):
    login(client, "admin@test")
    r = client.get("/api/squads/999999")
    assert r.status_code == 404
    assert r.json() == {"detail": "Squad introuvable"}
    r = client.get("/api/squads/999999", headers={"Accept-Language": "fr"})
    assert r.json() == {"detail": "Squad introuvable"}


def test_unauthenticated_in_english(client):
    r = client.get("/api/squads/1", headers=EN)
    assert r.status_code == 401
    assert r.json() == {"detail": "Not signed in"}


def test_bad_login_in_english(client, seeded):
    r = client.post("/api/auth/login", json={"email": "admin@test", "password": "nope"}, headers=EN)
    assert r.status_code == 401
    assert r.json() == {"detail": "Invalid credentials"}


def test_status_headers_and_codes_are_kept():
    from fastapi import FastAPI, HTTPException
    from fastapi.testclient import TestClient

    from app import errors

    mini = FastAPI()
    errors.install(mini)

    @mini.get("/fr")
    def fr():
        raise HTTPException(status_code=429, detail="Trop de tentatives de connexion. Réessayez plus tard.",
                            headers={"Retry-After": "60"})

    @mini.get("/code")
    def code():
        raise HTTPException(status_code=403, detail="access_pending")

    @mini.get("/obj")
    def obj():
        raise HTTPException(status_code=400, detail={"field": "Nom requis"})

    c = TestClient(mini)
    r = c.get("/fr", headers=EN)
    assert (r.status_code, r.headers["retry-after"]) == (429, "60")
    assert r.json() == {"detail": "Too many sign-in attempts. Try again later."}
    assert c.get("/fr").json() == {"detail": "Trop de tentatives de connexion. Réessayez plus tard."}
    assert c.get("/code", headers=EN).json() == {"detail": "access_pending"}
    assert c.get("/obj", headers=EN).json() == {"detail": {"field": "Nom requis"}}
    assert c.get("/missing", headers=EN).json() == {"detail": "Not Found"}
