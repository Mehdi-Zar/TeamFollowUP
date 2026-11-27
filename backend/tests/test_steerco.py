"""Steerco: platform snapshots, 12-month aggregation, backfill, lang-aware one-pager.

The reporting unit is the platform. Since 4.0 (ADR 0018) the figures are entered
by the tribe's Steerco leaders (the tribe leader by default, plus the designated
users), a month is validated then read-only, and reading is a persona capability
closed by default.
"""
from datetime import datetime, timezone
import re

from app.models import Platform, SteercoEntry, SteercoLeader
from app.platforms import default_template
from app.routers.steerco import (I18N, _aggregate, month_keys, _onepager,
                                 _render_pptx, _svg_line_chart)
from tests.conftest import login


def _enable(client):
    """Steerco module is off by default; turn it on as admin."""
    login(client, "admin@test")
    r = client.put("/api/admin/modules-config", json={"steerco": {"enabled": True}})
    assert r.status_code == 200, r.text


def _platform(db, seeded, name="Sovereign Platform", squads=("squad_a",), template=None) -> int:
    """A platform of tribe 1 with the named squads concerned and the standard slide."""
    ids = [seeded[s] for s in squads]
    from app.models import Squad
    p = Platform(tribe_id=seeded["t1"], name=name, display_order=1, steerco_enabled=True,
                 template=template or default_template())
    p.contributors = [db.get(Squad, i) for i in ids]
    db.add(p)
    db.commit()
    return p.id


# ---- pure helpers --------------------------------------------------------------

def test_month_keys():
    assert month_keys("2026-02", 3) == ["2025-12", "2026-01", "2026-02"]
    assert len(month_keys("2026-07", 12)) == 12


def test_svg_handles_gaps_and_empty():
    svg = _svg_line_chart({"labels": ["a", "b", "c"], "y_max": 100,
                           "series": [{"name": "x", "color": "#000", "data": [None, 40, 50]}]}, "no data")
    # A line, and one dot only: the latest month (a single month drew nothing).
    assert svg.startswith("<svg") and "<path" in svg and svg.count("<circle") == 1
    assert "no data" in _svg_line_chart({"series": []}, "no data")


def test_a_single_month_is_still_drawn():
    """Le premier steerco d'une plateforme n'a qu'un mois: sans point, la courbe
    n'avait rien a tracer et le graphique restait vide."""
    svg = _svg_line_chart({"labels": ["a", "b", "c"], "y_max": 100,
                           "series": [{"name": "x", "color": "#000", "data": [None, 40, None]}]}, "no data")
    assert "<circle" in svg


# ---- aggregation ---------------------------------------------------------------

def test_aggregate_builds_calendar_year_charts_and_annual_sla(db, seeded):
    pid = _platform(db, seeded)
    for p, users, inc in [("2026-05", 200, 10), ("2026-06", 210, 15), ("2026-07", 247, 13)]:
        db.add(SteercoEntry(platform_id=pid, period=p, data={
            "kpis": [{"label": "Users", "value": str(users), "trend": "up"}],
            "sla": {"services": ["Incidents"], "cells": [{"v": "99,4%", "s": "ok"}]},
            "incidents": str(inc)}))
    db.commit()
    rd = _aggregate(db, pid, "2026-07")
    # 12 columns = the calendar year, January to December: the chart always starts in
    # January (empty until May here), and the report month July sits at index 6.
    assert len(rd["kpi_chart"]["labels"]) == 12 and rd["kpi_chart"]["labels"][0] == "01/26"
    users_series = rd["kpi_chart"]["series"][0]
    assert users_series["data"][0] is None                       # January, no data yet
    assert users_series["data"][7] is None                       # August (future), empty
    seen = [v for v in users_series["data"] if v is not None]
    assert seen == [200, 210, 247]                               # RAW values, not a base-100 index
    assert rd["kpi_chart"]["y_min"] == 0                         # counts, floor at 0
    assert rd["incidents_chart"]["series"][0]["data"][6] == 13   # incidents at July, not the last column
    rows = rd["sla"]["rows"]
    assert [r["period"] for r in rows] == ["__current__", "__trailing__"]         # current + annual avg
    assert rd["kpis"][0]["value"] == "247"                                        # cards = current month


def test_change_vs_m1_and_sla_colour_are_computed(db, seeded):
    """Contributors enter raw numbers only: the variation vs M-1 comes from the
    previous month's snapshot, the SLA colour from the value (>90 green, 80-90 amber,
    <80 red). Anything stored by hand is overridden."""
    pid = _platform(db, seeded)
    db.add(SteercoEntry(platform_id=pid, period="2026-06", data={
        "kpis": [{"label": "Users", "value": "235"}, {"label": "K8aaS", "value": "8"},
                 {"label": "DBaaS", "value": "4"}]}))
    db.add(SteercoEntry(platform_id=pid, period="2026-07", data={
        # stale hand-entered values on purpose: they must be recomputed
        "kpis": [{"label": "Users", "value": "247", "trend": "down", "delta": "-99"},
                 {"label": "K8aaS", "value": "5"}, {"label": "DBaaS", "value": "4"},
                 {"label": "New", "value": "3"}],
        "sla": {"services": ["A", "B", "C", "D", "E"],
                "cells": [{"v": "99,4%", "s": "ko"}, {"v": "90%"}, {"v": "84,5%"},
                          {"v": "72%"}, {"v": ""}]}}))
    db.commit()
    rd = _aggregate(db, pid, "2026-07")
    assert [(k["trend"], k["delta"]) for k in rd["kpis"]] == [
        ("up", "+12"),      # 247 vs 235
        ("down", "-3"),     # 8 -> 5
        ("flat", "0"),      # unchanged
        ("flat", ""),       # no previous value, no variation shown
    ]
    cur = rd["sla"]["rows"][0]["cells"]
    assert [c["s"] for c in cur] == ["ok", "warn", "warn", "ko", None]   # 90 stays amber
    html = _onepager("Sovereign Platform", "2026-07", rd, I18N["en"])
    assert "▲ +12" in html and "b-ko" in html and "b-warn" in html


def test_sla_percentages_are_capped_at_100(client, db, seeded):
    """A SLA is a percentage: 100 is the ceiling, whatever is sent (typo, import)."""
    _enable(client)
    pid = _platform(db, seeded, template={"kpis": [], "sla": [{"label": "A"}, {"label": "B"}]})
    login(client, seeded["tribe"])
    r = client.put(f"/api/steerco/platform/{pid}?period=2026-07", json={"data": {
        "sla": {"services": ["A", "B"], "cells": [{"v": "994%"}, {"v": "99,4%"}]}}, "version": 0})
    assert r.status_code == 200, r.text
    assert [c["v"] for c in r.json()["data"]["sla"]["cells"]] == ["100%", "99,4%"]
    rd = _aggregate(db, pid, "2026-07")
    assert [c["v"] for c in rd["sla"]["rows"][0]["cells"]] == ["100%", "99,4%"]


def test_a_curve_out_of_scale_gets_its_own_axis_on_the_right(db, seeded):
    """Une Software Factory qui compte ses builds par milliers ecrasait les autres
    courbes: DBaaS a 12 et K8aaS a 30 se confondaient avec l'axe, sur une slide dont
    le seul objet est de montrer leur evolution. La lecture etait perdue pour quatre
    courbes sur cinq, au profit de la seule qui n'avait pas besoin du graphe.

    Les series sont donc coupees au plus grand ecart d'ordre de grandeur, et le
    groupe du haut se lit sur une seconde echelle, a droite."""
    pid = _platform(db, seeded)
    for i, period in enumerate(["2026-05", "2026-06", "2026-07"]):
        db.add(SteercoEntry(platform_id=pid, period=period, data={"kpis": [
            {"label": "Software Factory", "value": str(3800 + 100 * i)},
            {"label": "DBaaS", "value": str(10 + i)},
            {"label": "K8aaS", "value": str(28 + i)},
        ]}))
    db.commit()
    rd = _aggregate(db, pid, "2026-07")
    by_name = {s["name"]: s for s in rd["kpi_chart"]["series"]}
    assert by_name["Software Factory"].get("axis") == "right"
    assert by_name["DBaaS"].get("axis") is None and by_name["K8aaS"].get("axis") is None
    # Chaque axe n'a a tenir que son groupe: 30 a gauche, 4000 a droite.
    assert rd["kpi_chart"]["y_max"] == 30 and rd["kpi_chart"]["y2_max"] == 4000

    svg = _svg_line_chart(rd["kpi_chart"], "no data")
    assert ">4000<" in svg and ">30<" in svg, "les deux graduations hautes sont ecrites"
    # Chaque courbe est haute dans le cadre au lieu d'etre couchee sur l'axe: 3900 sur
    # 4000 a droite, 30 sur 40 a gauche, donc les deux dans le quart haut du graphe.
    paths = dict((color, d) for d, color in
                 re.findall(r'<path d="([^"]+)" fill="none" stroke="([^"]+)"', svg))
    tops = {c: min(float(pt.split()[1]) for pt in d.replace("M", "L").split("L")[1:])
            for c, d in paths.items()}
    # Par la couleur de la serie et non par un code ecrit ici: la palette peut
    # changer, ce qui se verifie est la hauteur du trace.
    top_of = lambda name: tops[by_name[name]["color"]]
    assert top_of("Software Factory") < 25, "lue a droite"
    assert top_of("K8aaS") < 60, "lue a gauche"

    # Et la legende dit quelle courbe se lit de quel cote, sinon le chiffre est
    # illisible. Elle le dit **une fois par echelle**: deux courbes a droite, et la
    # mention repetee derriere chacune disait deux fois la meme chose, en coutant
    # une ligne de legende prise sur la hauteur du graphe.
    html = _onepager("Sovereign Platform", "2026-07", rd, I18N["fr"])
    assert html.count("axe droit") == 1 and html.count("axe gauche") == 1
    # Le groupe de droite porte la seule courbe concernee, celui de gauche les deux
    # autres: l'ordre du rendu le dit, chaque nom suivant son en-tete.
    order = [html.index(s) for s in ("axe gauche", "DBaaS", "axe droit", "Software Factory")]
    assert order == sorted(order), html


def test_curves_of_the_same_order_keep_a_single_axis(db, seeded):
    """Un second axe se paie d'une colonne de chiffres a lire: il n'apparait que
    quand les courbes ne tiennent vraiment pas ensemble."""
    pid = _platform(db, seeded)
    db.add(SteercoEntry(platform_id=pid, period="2026-07", data={"kpis": [
        {"label": "DBaaS", "value": "12"}, {"label": "K8aaS", "value": "30"}]}))
    db.commit()
    rd = _aggregate(db, pid, "2026-07")
    assert "y2_max" not in rd["kpi_chart"]
    assert all(s.get("axis") is None for s in rd["kpi_chart"]["series"])
    assert "(échelle droite)" not in _onepager("Sovereign Platform", "2026-07", rd, I18N["fr"])


def test_a_series_flat_at_zero_does_not_send_the_others_to_the_right(db, seeded):
    """Un KPI pas encore ouvert vaut zero douze mois durant. Compare au suivant, il
    ouvre un ecart infini: la coupe s'y serait faite, et toutes les autres courbes
    seraient parties a droite pour rien."""
    pid = _platform(db, seeded)
    db.add(SteercoEntry(platform_id=pid, period="2026-07", data={"kpis": [
        {"label": "DBaaS", "value": "0"}, {"label": "K8aaS", "value": "30"},
        {"label": "Landing Zone", "value": "24"}]}))
    db.commit()
    rd = _aggregate(db, pid, "2026-07")
    assert "y2_max" not in rd["kpi_chart"]


def test_the_second_axis_survives_into_the_slide(db, seeded):
    """Le document du comite est la slide, pas la page: une echelle qui n'existerait
    qu'en HTML laisserait le PPTX avec le probleme qu'on vient de corriger."""
    from pptx import Presentation
    import io as _io
    pid = _platform(db, seeded)
    db.add(SteercoEntry(platform_id=pid, period="2026-07", data={"kpis": [
        {"label": "Software Factory", "value": "3800"}, {"label": "DBaaS", "value": "12"}]}))
    db.commit()
    rd = _aggregate(db, pid, "2026-07")
    deck = _render_pptx([{"squad_name": "Sovereign Platform", "data": rd}], "2026-07", I18N["fr"])
    slide = Presentation(_io.BytesIO(deck)).slides[0]
    charts = [sh.chart for sh in slide.shapes if sh.has_chart]
    xml = next(c._chartSpace.xml for c in charts if "Software Factory" in c._chartSpace.xml)
    plot = xml[xml.index("<c:plotArea"):]
    assert plot.count("<c:lineChart>") == 2, "un groupe par echelle"
    assert 'c:axPos val="r"' in plot and 'c:crosses val="max"' in plot, "l'axe est a droite"
    assert plot.count("<c:valAx>") == 2 and plot.count("<c:catAx>") == 2


def test_onepager_layout_and_translation(db, seeded):
    pid = _platform(db, seeded)
    db.add(SteercoEntry(platform_id=pid, period="2026-07", data={
        "kpis": [{"label": "Users", "value": "247"}],
        "sla": {"services": ["Incidents"], "cells": [{"v": "99,4%", "s": "ok"}]},
        "incidents": "13"}))
    db.commit()
    rd = _aggregate(db, pid, "2026-07")
    html_en = _onepager("Sovereign Platform", "2026-07", rd, I18N["en"])
    # left column (KPIs) comes before the SLA table; right column has the KPI chart
    assert html_en.index("kpi-row") < html_en.index(">SLA")   # KPI panel before the SLA panel
    assert "hdr" in html_en and "July 2026" in html_en          # header + spelled-out month
    # SLA rows are the current month + the annual average; the chart sub shows the year.
    assert "Current month" in html_en and "Annual average" in html_en and "KPI trend" in html_en
    assert "base 100" not in html_en                            # chart plots raw values, not an index
    html_fr = _onepager("Sovereign Platform", "2026-07", rd, I18N["fr"])
    assert "Mois en cours" in html_fr and "Moyenne annuelle" in html_fr and "Évolution KPI" in html_fr


def test_an_event_of_an_unexpected_shape_does_not_take_the_document_down(db, seeded):
    """Le relevé est un blob sans schema, et c'est assume: la forme peut evoluer
    sans migration. Les deux rendus appelaient pourtant `.get()` sur chaque
    evenement sans verifier que c'en etait un. Une chaine a cet endroit, et le
    comite n'avait plus de document du tout, ni page ni slide.

    Un lecteur tolerant est la contrepartie d'un ecrivain sans schema: ce qui n'est
    pas un dictionnaire se lit comme un texte, et le document sort.
    """
    pid = _platform(db, seeded)
    db.add(SteercoEntry(platform_id=pid, period="2026-07", data={
        "kpis": [{"label": "Users", "value": "247"}],
        "incidents": "13",
        # Ce qu'un import, un appel d'API ou une version anterieure peut avoir ecrit.
        "last_events": ["Bascule du socle", {"date": "12/07", "text": "Mise a jour"}],
        "next_events": [None],
    }))
    db.commit()
    rd = _aggregate(db, pid, "2026-07")

    html = _onepager("Sovereign Platform", "2026-07", rd, I18N["fr"])
    assert "Bascule du socle" in html, "le texte brut doit survivre a la lecture"
    assert "Mise a jour" in html, "et le voisin bien forme aussi"

    deck = _render_pptx([{"squad_name": "Sovereign Platform", "data": rd}], "2026-07", I18N["fr"])
    assert len(deck) > 10_000, "la slide doit se produire malgre la ligne mal formee"


# ---- platforms: declaration, contributors, template ----------------------------

def test_module_gate_blocks_when_disabled(client, seeded):
    login(client, "admin@test")
    assert client.get("/api/steerco/entries?period=2026-07").status_code == 404


# ---- who runs, who reads (ADR 0018) ----------------------------------------------

def test_the_tribe_leader_runs_the_steerco_of_their_tribe_by_default(client, db, seeded):
    _enable(client)
    login(client, seeded["tribe"])
    st = client.get("/api/auth/me/permissions").json()["steerco"]
    assert st["run"] is True and st["run_tribe_ids"] == [seeded["t1"]]
    r = client.post("/api/steerco/platforms", json={"name": "Sovereign Platform"})
    assert r.status_code == 201 and r.json()["tribe_id"] == seeded["t1"]
    # Not on another tribe.
    r = client.post("/api/steerco/platforms", json={"name": "X", "tribe_id": seeded["t2"]})
    assert r.status_code == 403


def test_a_squad_leader_designated_steerco_leader_keeps_their_role_and_runs_it(client, db, seeded):
    """The designation adds to the role: a squad leader stays a squad leader."""
    _enable(client)
    pid = _platform(db, seeded)
    login(client, seeded["sl_a"])
    assert client.get("/api/steerco/board?year=2026").status_code == 403
    assert client.put(f"/api/steerco/platform/{pid}?period=2026-07",
                      json={"data": {"incidents": "3"}, "version": 0}).status_code == 403

    login(client, seeded["tribe"])
    r = client.post("/api/steerco/leaders", json={"tribe_id": seeded["t1"], "user_id": seeded["sl_a_id"]})
    assert r.status_code == 201, r.text
    names = [x["display_name"] for x in r.json()["leaders"]]
    assert names == ["Tribe", "SL A"]                     # the tribe leader first, by default

    login(client, seeded["sl_a"])
    me = client.get("/api/auth/me").json()
    assert me["role"] == "squad_leader"
    r = client.put(f"/api/steerco/platform/{pid}?period=2026-07",
                   json={"data": {"incidents": "3"}, "version": 0})
    assert r.status_code == 200, r.text
    rows = client.get("/api/steerco/board?year=2026").json()["platforms"]
    assert rows[0]["months"][6]["fill"] == "partial"


def test_the_users_screen_badges_the_steerco_leaders(client, db, seeded):
    """Administration > Users shows who runs a Steerco, to whoever designates there."""
    _enable(client)
    db.add(SteercoLeader(user_id=seeded["sl_a_id"], tribe_id=seeded["t1"]))
    db.commit()
    login(client, seeded["tribe"])
    badges = client.get("/api/steerco/leaders/badges").json()
    assert set(badges) >= {str(seeded["sl_a_id"])}
    assert str(seeded["sl_b_id"]) not in badges
    login(client, seeded["sl_a"])                        # designates nowhere: nothing
    assert client.get("/api/steerco/leaders/badges").json() == {}


def test_a_steerco_leader_cannot_designate_another(client, db, seeded):
    _enable(client)
    db.add(SteercoLeader(user_id=seeded["sl_a_id"], tribe_id=seeded["t1"]))
    db.commit()
    login(client, seeded["sl_a"])
    r = client.post("/api/steerco/leaders", json={"tribe_id": seeded["t1"], "user_id": seeded["sl_b_id"]})
    assert r.status_code == 403
    assert client.get(f"/api/steerco/leaders?tribe_id={seeded['t1']}").status_code == 200


def test_only_the_admin_withdraws_the_tribe_leader_default(client, db, seeded):
    _enable(client)
    from app.models import User
    tl = db.query(User).filter(User.email == seeded["tribe"]).one()
    login(client, seeded["tribe"])
    assert client.delete(f"/api/steerco/leaders/{tl.id}?tribe_id={seeded['t1']}").status_code == 403

    login(client, "admin@test")
    r = client.delete(f"/api/steerco/leaders/{tl.id}?tribe_id={seeded['t1']}")
    assert r.status_code == 200
    assert r.json()["leaders"][0]["active"] is False
    login(client, seeded["tribe"])
    assert client.post("/api/steerco/platforms", json={"name": "P"}).status_code == 403
    # The tribe leader still designates (it is their tribe), and gets it back.
    login(client, "admin@test")
    r = client.post("/api/steerco/leaders", json={"tribe_id": seeded["t1"], "user_id": tl.id})
    assert r.json()["leaders"][0]["active"] is True


def test_reading_is_closed_by_default_and_opened_per_persona(client, db, seeded):
    """The slide shows degraded SLAs and risks before the committee: no persona
    reads it unless the administrator ticks "steerco" for it."""
    _enable(client)
    _platform(db, seeded)
    login(client, seeded["member"])
    assert client.get("/api/steerco/entries?period=2026-07").status_code == 403
    assert client.get("/api/steerco/document.html?period=2026-07").status_code == 403

    login(client, "admin@test")
    personas = client.get("/api/admin/personas").json()
    items = personas["personas"] if isinstance(personas, dict) else personas
    member = next(p for p in items if p["key"] == "member")
    assert member["caps"]["steerco"] is False
    member["caps"]["steerco"] = True
    r = client.put("/api/admin/personas", json={"personas": items})
    assert r.status_code == 200, r.text

    login(client, seeded["member"])
    assert client.get("/api/steerco/entries?period=2026-07").status_code == 200
    # Reading is not running.
    assert client.get("/api/steerco/board?year=2026").status_code == 403


def test_a_platform_groups_several_squads_into_one_slide(client, db, seeded):
    """Two squads concerned, one platform, one page in the consolidated doc."""
    _enable(client)
    login(client, seeded["tribe"])
    r = client.post("/api/steerco/platforms", json={
        "name": "Sovereign Platform", "squad_ids": [seeded["squad_a"], seeded["squad_b"]]})
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    assert [c["name"] for c in r.json()["squads"]] == ["Squad A", "Squad B"]
    assert "owner_squad_id" not in r.json()["template"]["kpis"][0]

    client.put(f"/api/steerco/platform/{pid}?period=2026-07",
               json={"data": {"kpis": [{"label": "Cloud Users", "value": "12"}]}, "version": 0})
    doc = client.get("/api/steerco/document.html?period=2026-07&lang=en")
    assert doc.status_code == 200
    assert doc.text.count("class='page'") + doc.text.count('class="page"') == 1
    assert "Sovereign Platform" in doc.text and "Squad A" not in doc.text


def test_the_squad_page_names_its_steerco_platforms(client, db, seeded):
    _enable(client)
    login(client, seeded["tribe"])
    pid = client.post("/api/steerco/platforms",
                      json={"name": "P", "squad_ids": [seeded["squad_a"]]}).json()["id"]
    assert client.get(f"/api/squads/{seeded['squad_a']}").json()["steerco_platforms"] == ["P"]
    client.put(f"/api/steerco/platforms/{pid}", json={"steerco_enabled": False})
    assert client.get(f"/api/squads/{seeded['squad_a']}").json()["steerco_platforms"] == []


def test_an_admin_creates_a_platform_without_naming_a_tribe(client, db, seeded):
    """An admin belongs to no tribe: the tribe comes from the first squad concerned."""
    _enable(client)
    login(client, "admin@test")
    r = client.post("/api/steerco/platforms", json={
        "name": "Sovereign Platform", "squad_ids": [seeded["squad_a"]]})
    assert r.status_code == 201, r.text
    assert r.json()["tribe_id"] == seeded["t1"]
    r = client.post("/api/steerco/platforms", json={"name": "Orpheline"})
    assert r.status_code == 400 and "tribe" in r.json()["detail"].lower()


def test_a_squad_of_another_tribe_cannot_be_linked(client, db, seeded):
    _enable(client)
    login(client, "admin@test")
    r = client.post("/api/steerco/platforms", json={
        "tribe_id": seeded["t1"], "name": "P", "squad_ids": [seeded["squad_c"]]})
    assert r.status_code == 400


def test_a_squad_leader_does_not_declare_platforms(client, db, seeded):
    _enable(client)
    login(client, seeded["sl_a"])
    assert client.post("/api/steerco/platforms", json={"name": "P"}).status_code == 403
    pid = _platform(db, seeded)
    assert client.put(f"/api/steerco/platforms/{pid}", json={"name": "X"}).status_code in (403, 404)
    assert client.delete(f"/api/steerco/platforms/{pid}").status_code in (403, 404)


# ---- writing a month: version, validation, reopening -----------------------------

def test_labels_come_from_the_template_not_from_the_payload(client, db, seeded):
    """A stale form must not rename the slide's rows: the template is the authority."""
    _enable(client)
    pid = _platform(db, seeded, template={"kpis": [{"label": "Users"}], "sla": []})
    login(client, seeded["tribe"])
    r = client.put(f"/api/steerco/platform/{pid}?period=2026-07",
                   json={"data": {"kpis": [{"label": "Renamed by a stale tab", "value": "3"}]},
                         "version": 0})
    assert r.json()["data"]["kpis"][0] == {"label": "Users", "value": "3"}


def test_a_save_on_a_stale_version_is_refused(client, db, seeded):
    """Two Steerco leaders on the same month: the second save, made on what they
    loaded before the first one, must not erase it silently."""
    _enable(client)
    pid = _platform(db, seeded)
    login(client, seeded["tribe"])
    first = client.put(f"/api/steerco/platform/{pid}?period=2026-07",
                       json={"data": {"incidents": "3"}, "version": 0})
    assert first.status_code == 200 and first.json()["version"] == 1
    stale = client.put(f"/api/steerco/platform/{pid}?period=2026-07",
                       json={"data": {"incidents": "9"}, "version": 0})
    assert stale.status_code == 409 and "Tribe" in stale.json()["detail"]
    ok = client.put(f"/api/steerco/platform/{pid}?period=2026-07",
                    json={"data": {"incidents": "9"}, "version": 1})
    assert ok.status_code == 200 and ok.json()["data"]["incidents"] == "9"


def test_a_validated_month_is_read_only_until_reopened_with_a_reason(client, db, seeded):
    _enable(client)
    pid = _platform(db, seeded)
    login(client, seeded["tribe"])
    url = f"/api/steerco/platform/{pid}"
    assert client.post(f"{url}/validate?period=2026-07").status_code == 400     # nothing in it
    v = client.put(f"{url}?period=2026-07", json={"data": {"incidents": "3"}, "version": 0}).json()["version"]
    r = client.post(f"{url}/validate?period=2026-07")
    assert r.status_code == 200 and r.json()["status"] == "validated" and r.json()["validated_by"] == "Tribe"
    assert client.put(f"{url}?period=2026-07",
                      json={"data": {"incidents": "4"}, "version": r.json()["version"]}).status_code == 409
    assert client.post(f"{url}/reopen?period=2026-07", json={"reason": ""}).status_code == 400
    r = client.post(f"{url}/reopen?period=2026-07", json={"reason": "Erreur sur les incidents"})
    assert r.status_code == 200 and r.json()["status"] == "draft" and r.json()["revised_at"]
    client.put(f"{url}?period=2026-07", json={"data": {"incidents": "4"}, "version": r.json()["version"]})
    # The document now says it was revised.
    html = client.get(f"/api/steerco/onepager.html?platform_id={pid}&period=2026-07&lang=en").text
    assert "revised on" in html
    from app.models import AuditLog
    reopen = db.query(AuditLog).filter(AuditLog.action == "steerco.reopen").one()
    assert "Erreur sur les incidents" in str(reopen.detail)
    assert v == 1


def test_validate_the_whole_month_leaves_empty_platforms_alone(client, db, seeded):
    _enable(client)
    p1 = _platform(db, seeded, name="P1")
    _platform(db, seeded, name="P2")
    login(client, seeded["tribe"])
    client.put(f"/api/steerco/platform/{p1}?period=2026-07", json={"data": {"incidents": "1"}, "version": 0})
    r = client.post(f"/api/steerco/validate?period=2026-07&tribe_id={seeded['t1']}").json()
    assert r["validated"] == ["P1"] and r["empty"] == ["P2"]


def test_the_board_gives_each_month_its_state(client, db, seeded):
    _enable(client)
    pid = _platform(db, seeded, template={"kpis": [{"label": "Users"}], "sla": [{"label": "A"}]})
    login(client, seeded["tribe"])
    client.put(f"/api/steerco/platform/{pid}?period=2026-06",
               json={"data": {"kpis": [{"value": "1"}], "sla": {"cells": [{"v": "99%"}]},
                              "incidents": "0"}, "version": 0})
    client.post(f"/api/steerco/platform/{pid}/validate?period=2026-06")
    client.put(f"/api/steerco/platform/{pid}?period=2026-07",
               json={"data": {"kpis": [{"value": "2"}]}, "version": 0})
    months = client.get("/api/steerco/board?year=2026").json()["platforms"][0]["months"]
    assert len(months) == 12
    assert (months[5]["fill"], months[5]["status"]) == ("complete", "validated")
    assert (months[6]["fill"], months[6]["filled_count"], months[6]["item_count"]) == ("partial", 1, 3)
    assert months[7]["fill"] == "empty"


def test_events_are_kept_as_entered(client, db, seeded):
    _enable(client)
    pid = _platform(db, seeded, template={"kpis": [], "sla": [{"label": "A"}]})
    login(client, seeded["tribe"])
    client.put(f"/api/steerco/platform/{pid}?period=2026-07", json={"data": {
        "last_events": [{"date": "01/07", "text": "Vu", "tag": "Incident", "sev": "red"},
                        {"date": "02/07", "text": "Autre", "sev": "bogus"}]}, "version": 0})
    events = client.get(f"/api/steerco/platform/{pid}?period=2026-07").json()["data"]["last_events"]
    assert [(e["text"], e["sev"]) for e in events] == [("Vu", "red"), ("Autre", "ice")]


def test_the_entries_list_says_where_each_platform_stands(client, db, seeded):
    _enable(client)
    pid = _platform(db, seeded)
    login(client, seeded["tribe"])
    client.put(f"/api/steerco/platform/{pid}?period=2026-07",
               json={"data": {"kpis": [{"label": "Cloud Users", "value": "247"}], "incidents": "3"},
                     "version": 0})
    row = client.get("/api/steerco/entries?period=2026-07").json()[0]
    assert row["platform_name"] == "Sovereign Platform" and row["filled"] is True
    assert row["fill"] == "partial" and row["status"] == "draft"


# ---- reporting flow --------------------------------------------------------------

def test_snapshot_backfill_history_and_document(client, db, seeded):
    _enable(client)
    pid = _platform(db, seeded)
    login(client, seeded["tribe"])
    assert client.put(f"/api/steerco/platform/{pid}?period=2026-07", json={"data": {
        "kpis": [{"label": "Cloud Users", "value": "247"}],
        "sla": {"services": ["Incidents"], "cells": [{"v": "99,4%", "s": "ok"}]},
        "incidents": "13"}, "version": 0}).status_code == 200
    # backfill two past months in one shot
    r = client.put(f"/api/steerco/platform/{pid}/history", json={"months": {
        "2026-06": {"kpis": [{"label": "Cloud Users", "value": "210"}], "incidents": "15"},
        "2026-05": {"kpis": [{"label": "Cloud Users", "value": "200"}], "incidents": "10"}}})
    assert r.status_code == 200 and r.json()["count"] == 2
    hist = client.get(f"/api/steerco/platform/{pid}/history?period=2026-07").json()
    assert len(hist["months"]) == 12
    # the month before January, for "take over the previous month" in January
    assert client.get(f"/api/steerco/platform/{pid}/history?period=2026-01").json()["previous"]["period"] == "2025-12"
    assert hist["previous"]["period"] == "2026-06"

    login(client, "admin@test")
    en = client.get(f"/api/steerco/onepager.html?platform_id={pid}&period=2026-07&lang=en")
    assert en.status_code == 200 and "KPI trend" in en.text and "247" in en.text
    fr = client.get(f"/api/steerco/onepager.html?platform_id={pid}&period=2026-07&lang=fr")
    assert "Évolution KPI" in fr.text
    assert client.get("/api/steerco/document.pptx?period=2026-07&lang=en").status_code == 200


def test_backfill_skips_validated_months(client, db, seeded):
    _enable(client)
    pid = _platform(db, seeded)
    login(client, seeded["tribe"])
    client.put(f"/api/steerco/platform/{pid}?period=2026-06", json={"data": {"incidents": "1"}, "version": 0})
    client.post(f"/api/steerco/platform/{pid}/validate?period=2026-06")
    r = client.put(f"/api/steerco/platform/{pid}/history", json={"months": {
        "2026-06": {"incidents": "9"}, "2026-05": {"incidents": "2"}}}).json()
    assert r["skipped"] == ["2026-06"] and r["count"] == 1
    assert client.get(f"/api/steerco/platform/{pid}?period=2026-06").json()["data"]["incidents"] == "1"


def test_entry_reports_monthly_fill_status(client, db, seeded):
    _enable(client)
    pid = _platform(db, seeded)
    login(client, seeded["tribe"])
    before = client.get(f"/api/steerco/platform/{pid}?period=2026-07").json()
    assert before["filled"] is False and before["updated_at"] is None and before["version"] == 0
    client.put(f"/api/steerco/platform/{pid}?period=2026-07",
               json={"data": {"kpis": [{"label": "Cloud Users", "value": "1"}]}, "version": 0})
    after = client.get(f"/api/steerco/platform/{pid}?period=2026-07").json()
    assert after["filled"] is True and after["updated_at"] and after["updated_by"] == "Tribe"


def test_preview_uses_unsaved_data_without_persisting(client, db, seeded):
    _enable(client)
    pid = _platform(db, seeded)
    login(client, seeded["tribe"])
    r = client.post(f"/api/steerco/platform/{pid}/preview.html?period=2026-07&lang=en",
                    json={"kpis": [{"label": "Users", "value": "997"}],
                          "sla": {"services": ["Incidents"], "cells": [{"v": "99,4%", "s": "ok"}]},
                          "incidents": "3"})
    assert r.status_code == 200 and "997" in r.text
    assert client.get(f"/api/steerco/platform/{pid}?period=2026-07").json()["filled"] is False


def test_backfill_requires_edit_rights(client, db, seeded):
    _enable(client)
    pid = _platform(db, seeded)
    login(client, seeded["member"])
    assert client.put(f"/api/steerco/platform/{pid}/history",
                      json={"months": {"2026-06": {"incidents": "3"}}}).status_code in (403, 404)


# ---- mails -------------------------------------------------------------------------

def test_the_pack_leaves_only_once_every_platform_is_validated(client, db, seeded, monkeypatch):
    _enable(client)
    pid = _platform(db, seeded)
    sent = []
    import app.mail as mail
    monkeypatch.setattr(mail, "send_email", lambda cfg, to, subject, body, **kw: sent.append((to, kw.get("attachment"))) or True)
    login(client, seeded["tribe"])
    assert client.post(f"/api/steerco/send?period=2026-07&tribe_id={seeded['t1']}").status_code == 400  # no one
    r = client.put(f"/api/steerco/mail?tribe_id={seeded['t1']}", json={"recipients": ["comite@example.com"]})
    assert r.status_code == 200 and r.json()["recipients"] == ["comite@example.com"]
    assert client.put(f"/api/steerco/mail?tribe_id={seeded['t1']}",
                      json={"recipients": ["pas une adresse"]}).status_code == 400
    client.put(f"/api/steerco/platform/{pid}?period=2026-07", json={"data": {"incidents": "1"}, "version": 0})
    r = client.post(f"/api/steerco/send?period=2026-07&tribe_id={seeded['t1']}")
    assert r.status_code == 409 and "Sovereign Platform" in r.json()["detail"]
    client.post(f"/api/steerco/platform/{pid}/validate?period=2026-07")
    r = client.post(f"/api/steerco/send?period=2026-07&tribe_id={seeded['t1']}")
    assert r.status_code == 200, r.text
    assert sent and sent[0][0] == "comite@example.com" and sent[0][1][0].endswith(".pptx")


def test_the_monthly_reminder_goes_once_and_only_when_something_is_left(client, db, seeded, monkeypatch):
    from datetime import date
    from app import steercomail
    _enable(client)
    pid = _platform(db, seeded)
    sent = []
    import app.mail as mail
    monkeypatch.setattr(mail, "send_email", lambda cfg, to, subject, body, **kw: sent.append((to, subject)) or True)
    assert steercomail.send_due_reminders(db, date(2026, 8, 3)) == []          # before the day
    assert steercomail.send_due_reminders(db, date(2026, 8, 5)) == ["Tribe One"]
    assert [to for to, _ in sent] == ["tribe@test"]
    sent.clear()
    assert steercomail.send_due_reminders(db, date(2026, 8, 6)) == [] and not sent   # once
    # Next month, everything validated: nothing to say.
    login(client, seeded["tribe"])
    client.put(f"/api/steerco/platform/{pid}?period=2026-08", json={"data": {"incidents": "1"}, "version": 0})
    client.post(f"/api/steerco/platform/{pid}/validate?period=2026-08")
    db.expire_all()
    steercomail.send_due_reminders(db, date(2026, 9, 10))
    assert not sent


# ---- Excel collection ------------------------------------------------------------

def test_template_columns_are_the_charted_window(seeded):
    """The workbook's 12 month columns must be exactly the window the one-pager charts
    read: the report year's calendar months, January to December, so the filled months
    line up with the charted months and the charts start in January."""
    import io
    from openpyxl import load_workbook
    from app.steerco_import import _month_label, template_bytes
    from app.routers.steerco import year_months

    wb = load_workbook(io.BytesIO(template_bytes("2026-07")))
    headers = [wb["KPIs"].cell(1, 2 + j).value for j in range(12)]
    expected = [_month_label(k) for k in year_months("2026-07")]
    expected[6] += "*"                                  # July is the report month
    assert headers == expected
    assert headers[0] == "Janv 26"                      # always January, not a rolling start
    assert headers[6].endswith("*") and headers[-1] == "Déc 26"


def test_excel_template_and_import(client, seeded, db):
    """Admin downloads the blank template, uploads a filled one, and it lands as
    SteercoEntry snapshots for the named platform (Admin > Import)."""
    import io
    from openpyxl import load_workbook
    from app.steerco_import import template_bytes

    pid = _platform(db, seeded, name="Sovereign Platform")
    _enable(client)
    login(client, "admin@test")
    r = client.get("/api/steerco/import/template")
    assert r.status_code == 200 and r.content[:2] == b"PK"        # a real .xlsx (zip)

    # fill it: platform name + a couple of months of one KPI + current SLA + an event.
    # Columns are the calendar year: B = Jan ... G = Jun, H = Jul (the report month).
    wb = load_workbook(io.BytesIO(template_bytes("2026-07")))
    wb["Infos"]["B2"] = "Sovereign Platform"; wb["Infos"]["B3"] = "2026-07"
    wb["KPIs"]["G2"] = 118; wb["KPIs"]["H2"] = 120          # Cloud Users Jun, Jul (current)
    wb["SLA"]["H2"] = 99.2                                   # Incidents, current month
    wb["Incidents"]["H2"] = 4
    wb["Evenements passes"]["A2"] = "12/07"; wb["Evenements passes"]["C2"] = "Incident majeur"
    wb["Evenements passes"]["D2"] = "Attention"
    buf = io.BytesIO(); wb.save(buf); buf.seek(0)

    r = client.post("/api/steerco/import",
                    files={"file": ("steerco.xlsx", buf.getvalue(),
                                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
    assert r.status_code == 200, r.text
    s = r.json()
    assert s["platform"] == "Sovereign Platform" and s["period"] == "2026-07" and s["months"] >= 2

    # persisted + feeds the one-pager
    rd = _aggregate(db, pid, "2026-07")
    assert rd["kpis"][0]["value"] == "120"
    assert rd["sla"]["rows"][0]["cells"][0]["s"] == "ok"       # 99,2% -> green, computed
    seen = [v for v in rd["kpi_chart"]["series"][0]["data"] if v is not None]
    assert seen == [118, 120]                               # RAW Jun + Jul values (Cloud Users)
    # The imported event's severity reaches the one-pager as a coloured chip.
    html = _onepager("Sovereign Platform", "2026-07", rd, I18N["fr"])
    assert "Incident majeur" in html and "#FBF0D9" in html   # "Attention" -> amber chip


def test_an_old_workbook_saying_squad_still_imports(client, seeded, db):
    """Files already in circulation carry a "Squad" label; they must keep working."""
    import io
    from openpyxl import load_workbook
    from app.steerco_import import template_bytes

    _platform(db, seeded, name="Sovereign Platform")
    wb = load_workbook(io.BytesIO(template_bytes("2026-07")))
    wb["Infos"]["A2"] = "Squad (nom exact dans l'app)"
    wb["Infos"]["B2"] = "Sovereign Platform"; wb["Infos"]["B3"] = "2026-07"
    wb["KPIs"]["H2"] = 7
    buf = io.BytesIO(); wb.save(buf)

    _enable(client)
    login(client, "admin@test")
    r = client.post("/api/steerco/import",
                    files={"file": ("s.xlsx", buf.getvalue(), "application/octet-stream")})
    assert r.status_code == 200, r.text


def test_template_matches_what_the_platform_reports(client, db, seeded):
    """A platform's workbook must propose ITS rows (name pre-filled, its KPI / SLA
    lines from the slide template), not a canned list."""
    import io
    from openpyxl import load_workbook

    sid = seeded["squad_a"]
    pid = _platform(db, seeded, name="Sovereign Platform", template={
        "kpis": [{"label": "Cloud Users", "owner_squad_id": sid},
                 {"label": "Terraform", "owner_squad_id": sid}],
        "sla": [{"label": "Incidents", "owner_squad_id": sid},
                {"label": "Vault", "owner_squad_id": sid}],
        "incidents": {"owner_squad_id": sid}})

    _enable(client)
    login(client, "admin@test")
    r = client.get(f"/api/steerco/import/template?platform_id={pid}")
    assert r.status_code == 200
    wb = load_workbook(io.BytesIO(r.content))
    assert wb["Infos"]["B2"].value == "Sovereign Platform"                       # name pre-filled
    assert [wb["KPIs"].cell(i, 1).value for i in (2, 3)] == ["Cloud Users", "Terraform"]
    assert [wb["SLA"].cell(i, 1).value for i in (2, 3)] == ["Incidents", "Vault"]
    # without a platform, the standard structure is still served
    generic = load_workbook(io.BytesIO(client.get("/api/steerco/import/template").content))
    assert generic["KPIs"]["A2"].value == "Cloud Users" and not generic["Infos"]["B2"].value


def test_import_never_deletes_what_was_entered_in_the_app(client, db, seeded):
    """The workbook adds and updates; it must not wipe a KPI, an SLA service or the
    events entered in the app just because the file does not mention them."""
    import io
    from openpyxl import load_workbook
    from app.steerco_import import template_bytes

    pid = _platform(db, seeded, name="Sovereign Platform")
    db.add(SteercoEntry(platform_id=pid, period="2026-07", data={
        "kpis": [{"label": "Cloud Users", "value": "247"}, {"label": "Terraform", "value": "42"}],
        "sla": {"services": ["Vault"], "cells": [{"v": "95,0%"}]},
        "last_events": [{"date": "01/07", "text": "Saisi dans l'app"}]}))
    db.commit()

    # the generic template knows nothing about Terraform, Vault or the event.
    # Calendar-year columns: July (the report month) is column 8 (H).
    wb = load_workbook(io.BytesIO(template_bytes("2026-07")))
    wb["Infos"]["B2"] = "Sovereign Platform"; wb["Infos"]["B3"] = "2026-07"
    wb["KPIs"].cell(2, 8, 250)                       # updates Cloud Users only (July column)
    wb["KPIs"]["A7"] = "Nouveau KPI"; wb["KPIs"].cell(7, 8, 5)      # a row added by hand
    buf = io.BytesIO(); wb.save(buf)

    _enable(client)
    login(client, "admin@test")
    r = client.post("/api/steerco/import",
                    files={"file": ("s.xlsx", buf.getvalue(), "application/octet-stream")})
    assert r.status_code == 200, r.text
    assert r.json()["kept_kpis"] == ["Terraform"]     # preserved AND reported to the admin

    db.expire_all()
    data = (db.query(SteercoEntry)
            .filter(SteercoEntry.platform_id == pid, SteercoEntry.period == "2026-07").one()).data
    by_label = {k["label"]: k["value"] for k in data["kpis"]}
    assert by_label["Cloud Users"] == "250"          # updated by the file
    assert by_label["Terraform"] == "42"             # untouched, not deleted
    assert by_label["Nouveau KPI"] == "5"            # a row added in Excel is picked up
    assert data["sla"]["services"] == ["Vault"]      # service kept, footnote not read as one
    assert len(data["last_events"]) == 1             # empty event sheet does not wipe events


def test_import_leaves_a_validated_month_as_the_committee_saw_it(client, db, seeded):
    import io
    from openpyxl import load_workbook
    from app.steerco_import import template_bytes

    pid = _platform(db, seeded, name="Sovereign Platform")
    db.add(SteercoEntry(platform_id=pid, period="2026-06", status="validated",
                        data={"kpis": [{"label": "Cloud Users", "value": "200"}]}))
    db.commit()
    wb = load_workbook(io.BytesIO(template_bytes("2026-07")))
    wb["Infos"]["B2"] = "Sovereign Platform"; wb["Infos"]["B3"] = "2026-07"
    wb["KPIs"].cell(2, 7, 999)                       # June column: validated, must not move
    wb["KPIs"].cell(2, 8, 250)                       # July column: a draft, updated
    buf = io.BytesIO(); wb.save(buf)

    _enable(client)
    login(client, seeded["tribe"])
    r = client.post("/api/steerco/import",
                    files={"file": ("s.xlsx", buf.getvalue(), "application/octet-stream")})
    assert r.status_code == 200, r.text
    assert "2026-06" in r.json()["skipped_validated"]
    db.expire_all()
    june = db.query(SteercoEntry).filter_by(platform_id=pid, period="2026-06").one()
    assert june.data["kpis"][0]["value"] == "200"


def test_import_rejects_a_malformed_report_month(seeded):
    """The report month drives the 12 collected columns, so a non "AAAA-MM" value must
    fail loudly instead of silently importing into the wrong months."""
    import io
    import pytest
    from openpyxl import load_workbook
    from app.steerco_import import parse_workbook, template_bytes

    wb = load_workbook(io.BytesIO(template_bytes("2026-07")))
    wb["Infos"]["B2"] = "Sovereign Platform"; wb["Infos"]["B3"] = "juillet 2026"
    buf = io.BytesIO(); wb.save(buf)
    with pytest.raises(ValueError, match="AAAA-MM"):
        parse_workbook(buf.getvalue())


def test_import_unknown_platform_is_rejected(client, seeded):
    import io
    from openpyxl import load_workbook
    from app.steerco_import import template_bytes

    _enable(client)
    login(client, "admin@test")
    wb = load_workbook(io.BytesIO(template_bytes()))
    wb["Infos"]["B2"] = "No Such Platform"; wb["Infos"]["B3"] = "2026-07"
    buf = io.BytesIO(); wb.save(buf)
    r = client.post("/api/steerco/import",
                    files={"file": ("s.xlsx", buf.getvalue(), "application/octet-stream")})
    assert r.status_code == 400 and "introuvable" in r.json()["detail"].lower()


def test_a_period_is_a_month(client, db, seeded):
    """« abc » or « 2026-13 » used to fail as a 500 in the month arithmetic, or be
    stored as a period no chart reads."""
    _enable(client)
    pid = _platform(db, seeded)
    login(client, seeded["tribe"])
    for bad in ("abc", "2026-13", "2026-7"):
        assert client.get(f"/api/steerco/platform/{pid}/history?period={bad}").status_code == 422
    r = client.put(f"/api/steerco/platform/{pid}/history", json={"months": {"nope": {}}})
    assert r.status_code == 422, r.text
    assert client.get(f"/api/steerco/platform/{pid}/history?period=2026-07").status_code == 200


def test_the_slide_legend_sits_under_the_chart_grouped_by_axis(db, seeded):
    """La legende de PowerPoint se posait sur la courbe, et « (right axis) » repete
    derriere chaque serie l'etalait sur trois lignes. Elle est dessinee sous le
    graphe, groupee par echelle, et le graphe lui cede juste sa hauteur."""
    from pptx import Presentation
    import io as _io
    pid = _platform(db, seeded)
    db.add(SteercoEntry(platform_id=pid, period="2026-07", data={"kpis": [
        {"label": "Software Factory", "value": "3800"}, {"label": "DBaaS", "value": "12"}]}))
    db.commit()
    rd = _aggregate(db, pid, "2026-07")
    slide = Presentation(_io.BytesIO(_render_pptx([{"squad_name": "P", "data": rd}], "2026-07", I18N["en"]))).slides[0]
    chart_shape = next(sh for sh in slide.shapes if sh.has_chart and "Software Factory" in sh.chart._chartSpace.xml)
    assert not chart_shape.chart.has_legend
    legend = next(sh for sh in slide.shapes if sh.has_text_frame and "RIGHT AXIS" in sh.text_frame.text)
    text = legend.text_frame.text
    assert "LEFT AXIS" in text and "DBaaS" in text and "Software Factory" in text
    assert "(right axis)" not in text
    # Right under the chart, inside the same box.
    assert legend.top >= chart_shape.top + chart_shape.height - 10
    assert legend.left == chart_shape.left and legend.width == chart_shape.width


def test_reporting_messages_offered_to_the_events_step(client, db, seeded):
    """The events step offers the key messages of the platform's squads for the
    period's year, newest first, the same text once, other squads' left out."""
    from app.models import KeyMessage
    _enable(client)
    pid = _platform(db, seeded)
    for i, (sq, year, text) in enumerate([("squad_a", 2026, "Vendor slipping"),
                                          ("squad_a", 2026, "Go-live done"),
                                          ("squad_a", 2026, "vendor  slipping"),
                                          ("squad_a", 2025, "Last year"),
                                          ("squad_b", 2026, "Not this platform")]):
        db.add(KeyMessage(squad_id=seeded[sq], year=year, kind="risk", text=text, display_order=i,
                          created_at=datetime(year, 3, 1 + i, tzinfo=timezone.utc)))
    db.commit()
    login(client, seeded["tribe"])
    r = client.get(f"/api/steerco/platform/{pid}/messages?period=2026-04")
    assert r.status_code == 200, r.text
    assert [m["text"] for m in r.json()] == ["vendor  slipping", "Go-live done"]
    assert r.json()[0]["squad_name"] and r.json()[0]["kind"] == "risk"


# ---- contributors (ADR 0019) ---------------------------------------------------

def test_a_contributor_fills_in_their_platform_and_nothing_else(client, db, seeded):
    """Named on one platform by a Steerco leader: they read and write that month,
    see no other platform, and cannot validate, send or change the settings."""
    _enable(client)
    mine = _platform(db, seeded, name="Mine")
    other = _platform(db, seeded, name="Other")
    login(client, seeded["tribe"])                     # a Steerco leader by default
    r = client.put(f"/api/steerco/platforms/{mine}", json={"contributor_user_ids": [seeded["sl_b_id"]]})
    assert r.status_code == 200, r.text
    assert [c["id"] for c in r.json()["contributors"]] == [seeded["sl_b_id"]]

    login(client, seeded["sl_b"])
    rights = client.get("/api/auth/me/permissions").json()["steerco"]
    assert rights["contribute"] is True and rights["contribute_platform_ids"] == [mine]
    listed = client.get(f"/api/steerco/entries?period=2026-07&tribe_id={seeded['t1']}").json()
    assert [e["platform_id"] for e in listed] == [mine]
    assert listed[0]["can_edit"] is True and listed[0]["can_run"] is False

    r = client.put(f"/api/steerco/platform/{mine}?period=2026-07",
                   json={"data": {"incidents": "4"}, "version": 0})
    assert r.status_code == 200, r.text
    assert client.put(f"/api/steerco/platform/{other}?period=2026-07",
                      json={"data": {"incidents": "4"}, "version": 0}).status_code == 404
    assert client.post(f"/api/steerco/platform/{mine}/validate?period=2026-07").status_code == 403
    assert client.post("/api/steerco/platforms", json={"name": "P", "tribe_id": seeded["t1"]}).status_code == 403
    assert client.put(f"/api/steerco/platforms/{mine}", json={"name": "X"}).status_code == 403
    assert client.post(f"/api/steerco/send?period=2026-07&tribe_id={seeded['t1']}").status_code == 403


def test_removing_a_contributor_closes_the_platform_to_them(client, db, seeded):
    _enable(client)
    pid = _platform(db, seeded, name="Mine")
    login(client, seeded["tribe"])
    client.put(f"/api/steerco/platforms/{pid}", json={"contributor_user_ids": [seeded["sl_b_id"]]})
    client.put(f"/api/steerco/platforms/{pid}", json={"contributor_user_ids": []})
    login(client, seeded["sl_b"])
    assert client.get(f"/api/steerco/platform/{pid}?period=2026-07").status_code == 403


def test_the_reminder_reaches_a_contributor_with_their_platforms_only(db, seeded, monkeypatch):
    from datetime import date
    from app import steercomail
    from app.models import SteercoContributor
    from app.modulesconfig import get_modules
    mine = _platform(db, seeded, name="Mine")
    _platform(db, seeded, name="Other")
    db.add(SteercoContributor(user_id=seeded["sl_b_id"], platform_id=mine))
    db.commit()
    monkeypatch.setattr("app.modulesconfig.is_active", lambda mods, key: True)
    sent = []
    monkeypatch.setattr("app.mail.send_email",
                        lambda smtp, to, subject, body, **k: sent.append((to, body)) or True)
    steercomail.send_due_reminders(db, today=date(2026, 8, 6))
    from app.models import User
    email = db.get(User, seeded["sl_b_id"]).email
    theirs = [h for to, h in sent if to == email]
    assert len(theirs) == 1 and "Mine" in theirs[0] and "Other" not in theirs[0]
