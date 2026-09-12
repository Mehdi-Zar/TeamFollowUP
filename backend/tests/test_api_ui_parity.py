"""L'API et l'interface doivent se couvrir l'une l'autre, dans les deux sens.

Une route servie qu'aucun ecran n'appelle est une fonctionnalite que personne ne
peut utiliser: elle a coute son code, ses tests et sa maintenance, et elle ment sur
ce que l'application sait faire. C'est ainsi que l'avancement trimestriel a vecu,
affiche par trois ecrans, modifiable par aucun.

Un chemin appele par l'interface qu'aucune route ne sert est l'inverse: un bouton
qui repond 404 le jour ou quelqu'un clique dessus.

Ce test compare les CHEMINS, pas les verbes: les appels de l'interface passent par
des generiques TypeScript, des litteraux de gabarit et des concatenations, et en
extraire le verbe de facon fiable produit surtout du faux positif. Un chemin cite
dans les sources compte comme atteignable.
"""
import pathlib
import re

from app.main import app

SRC = pathlib.Path(__file__).resolve().parents[2] / "frontend" / "src"

# Routes qui n'ont deliberement pas d'ecran, avec la raison. Une entree ici est une
# decision, pas un oubli: la liste est courte et doit le rester.
NO_SCREEN_ON_PURPOSE: dict[str, str] = {
    # (vide pour l'instant: tout ce que l'API sert est atteignable depuis l'ecran)
}


def _norm(url: str) -> str:
    """Ramene un litteral d'appel au chemin de route qu'il vise.

    `${id}` dans le chemin devient un segment; une chaine de requete ou un ternaire
    ouvert est coupe, il ne fait pas partie du chemin.
    """
    url = re.sub(r"\$\{[^}]*\}", "{}", url)
    url = re.split(r"[?#$]", url)[0]
    url = re.sub(r"\{[^}]*\}", "{}", url)
    url = re.sub(r"(?<!/)\{\}$", "", url)
    url = re.sub(r"/\d+", "/{}", url)
    return url.rstrip("/")


def _covers(ui: str, api: str) -> bool:
    """Le chemin cite par l'interface atteint-il cette route ?

    Exact, ou bien la route ajoute un suffixe au DERNIER segment: l'interface
    construit `/api/org/export.${fmt}` et `/api/admin/log-export-config/${action}`,
    donc le litteral s'arrete avant l'extension ou l'action. Le suffixe est limite
    au dernier segment, sinon `/api/squads/{}` couvrirait tout ce qui pend dessous
    et le test ne verrait plus aucun orphelin.
    """
    if ui == api:
        return True
    ui_head, _, ui_last = ui.rpartition("/")
    api_head, _, api_last = api.rpartition("/")
    if ui_head != api_head:
        return False
    pattern = "^" + "".join(".+?" if part == "{}" else re.escape(part)
                            for part in re.split(r"(\{\})", ui_last) if part)
    return re.match(pattern, api_last) is not None


def _api_paths() -> set[str]:
    return {_norm(getattr(r, "path", "")) for r in app.routes
            if getattr(r, "path", "").startswith("/api")}


def _ui_paths() -> dict[str, set[str]]:
    literal = re.compile(r"""['"`](/api/[^'"`]*)['"`]""")
    partial = re.compile(r"""['"`](/api/[A-Za-z0-9_\-/${}.]*)""")
    out: dict[str, set[str]] = {}
    for path in sorted(SRC.rglob("*.ts*")):
        if path.name.endswith((".test.ts", ".test.tsx")):
            continue
        text = path.read_text(encoding="utf-8")
        for raw in set(literal.findall(text)) | set(partial.findall(text)):
            out.setdefault(_norm(raw), set()).add(path.relative_to(SRC).as_posix())
    return out


def test_every_served_route_is_reachable_from_a_screen():
    """Une route sans ecran est une fonctionnalite que personne ne peut utiliser."""
    ui = set(_ui_paths())
    orphans = sorted(api for api in _api_paths()
                     if api not in NO_SCREEN_ON_PURPOSE
                     and not any(_covers(u, api) for u in ui))
    assert orphans == [], (
        "ces routes ne sont appelees par aucun ecran: ouvrez-les dans l'interface, "
        "supprimez-les, ou justifiez-les dans NO_SCREEN_ON_PURPOSE"
    )


def test_every_path_the_interface_calls_is_served():
    """Un chemin sans route est un bouton qui repondra 404 le jour du clic."""
    api = _api_paths()
    unknown = sorted(u for u, files in _ui_paths().items()
                     if not any(_covers(u, a) for a in api))
    assert unknown == [], "ces chemins ne correspondent a aucune route servie"


def test_the_comparison_actually_compares_something():
    """Chaque filtre ci-dessus est facile a resserrer jusqu'a un test toujours vert."""
    api, ui = _api_paths(), _ui_paths()
    assert len(api) > 120 and len(ui) > 120
    assert "/api/squads/{}/quarter-progress" in api
    # Le suffixe dynamique est couvert, mais pas n'importe quoi en dessous.
    assert _covers("/api/org/export.", "/api/org/export.html")
    assert _covers("/api/reports/{}.", "/api/reports/weekly.pptx")
    assert not _covers("/api/squads/{}", "/api/squads/{}/actions")
    assert not _covers("/api/squads", "/api/tribes")


def test_the_quarter_comment_is_the_part_a_person_writes(client, db, seeded):
    """Le pourcentage est calcule, le commentaire est saisi: les deux doivent l'etre
    par le bon cote.

    L'endpoint acceptait un pourcentage a la main qu'aucun ecran ne relisait: la
    valeur affichee partout vient des jalons termines. Un editeur pour ce nombre
    aurait reintroduit le chiffre qui derive de la realite sans que personne le voie.
    """
    from app.models import RoadmapItem
    from tests.conftest import login

    sid = seeded["squad_a"]
    db.add(RoadmapItem(squad_id=sid, year=2026, quarter=1, title="Fait", status="done"))
    db.add(RoadmapItem(squad_id=sid, year=2026, quarter=1, title="En cours", status="on_track"))
    db.commit()

    login(client, seeded["sl_a"])
    r = client.put(f"/api/squads/{sid}/quarter-progress",
                   json={"year": 2026, "quarter": 1, "comment": "Le socle a pris deux semaines"})
    assert r.status_code == 200, r.text
    # Stocke = derive: un jalon sur deux est termine.
    assert r.json()["progress_pct"] == 50

    detail = client.get(f"/api/squads/{sid}?year=2026").json()["quarter_progress"]["1"]
    assert detail["comment"] == "Le socle a pris deux semaines"
    assert detail["progress_pct"] == 50          # ce que l'ecran affiche, et il concorde


def test_an_api_caller_may_still_send_its_own_percentage(client, db, seeded):
    """Compatibilite: un appelant qui envoie encore le nombre n'est pas casse."""
    from tests.conftest import login

    sid = seeded["squad_a"]
    login(client, seeded["sl_a"])
    r = client.put(f"/api/squads/{sid}/quarter-progress",
                   json={"year": 2026, "quarter": 2, "progress_pct": 80, "comment": None})
    assert r.status_code == 200 and r.json()["progress_pct"] == 80
