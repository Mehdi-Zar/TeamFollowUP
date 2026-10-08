"""Studio des exports (docs/35): templates that lay out the documents.

What these tests hold:

* a document nobody customised is, to the XML, the deck the product always made;
* every switch of a template changes what it says it changes, and nothing else;
* inheritance is by difference, and a parent's lock wins over a child's change;
* the rights: the administrator everywhere, a tribe leader on their tribe, a squad
  leader on their squad in simple mode, a member nowhere;
* the preview is drawn from the deck itself and reports what a slide cannot afford.
"""
from __future__ import annotations

import base64
import io
import re
import zipfile
from datetime import datetime, timezone

import pytest

from app import exportengine as E
from app import exportspec as X
from app import report as report_mod
from tests.conftest import login

YEAR = datetime.now(timezone.utc).year


def _prs(blob):
    pptx = pytest.importorskip("pptx")
    return pptx.Presentation(io.BytesIO(blob))


def _text(slide):
    out = []
    for sh in slide.shapes:
        if sh.has_text_frame:
            out.append(sh.text_frame.text)
        if getattr(sh, "has_table", False) and sh.has_table:
            out += [c.text for row in sh.table.rows for c in row.cells]
    return "\n".join(out)


def _xml(blob):
    z = zipfile.ZipFile(io.BytesIO(blob))
    return {n: re.sub(r"\d{1,2}:\d{2}", "HH:MM", z.read(n).decode("utf8"))
            for n in sorted(z.namelist()) if n.startswith("ppt/slides/slide") and n.endswith(".xml")}


def _ctx(kind, **providers):
    return E.Context(doc_kind=kind, lang="fr", scope_name="Tribe One", year=YEAR,
                     providers={k: (lambda v=v: v) for k, v in providers.items()})


def _sec(spec, sid):
    return next(s for s in spec["sections"] if s["id"] == sid)


# --------------------------------------------------------------------------
# The Standard template is the deck the product always made
# --------------------------------------------------------------------------
def test_standard_templates_render_the_legacy_decks_to_the_xml(db, seeded):
    pytest.importorskip("pptx")
    now = datetime(YEAR, 6, 15, 10, tzinfo=timezone.utc)
    data = report_mod.build_report_data(db, None, YEAR, 7, now=now, lang="fr")
    for kind, legacy in (("dashboard", report_mod.render_pptx({**data, "doc": "dashboard"})),
                         ("weekly", report_mod.render_pptx({**data, "doc": "report"})),
                         ("roadmap", report_mod.render_roadmap_pptx(data))):
        doc = {**data, "doc": "dashboard"} if kind == "dashboard" else data
        studio = E.render(X.system_spec(kind), _ctx(kind, report=doc))
        assert _xml(studio) == _xml(legacy), kind


def test_an_export_without_assignment_uses_standard(client, db, seeded):
    login(client, seeded["admin"])
    r = client.get("/api/exports/effective", params={"doc_kind": "dashboard", "tribe_id": seeded["t1"]})
    assert r.status_code == 200 and r.json()["source"] == "standard"
    r = client.get("/api/reports/dashboard.pptx", params={"tribe_id": seeded["t1"]})
    assert r.status_code == 200
    assert f'dashboard_{YEAR}.pptx' in r.headers["content-disposition"]


# --------------------------------------------------------------------------
# Switches
# --------------------------------------------------------------------------
def _report(db, squad=None):
    return report_mod.build_report_data(db, None, YEAR, 7, squad_id=squad, lang="fr")


def test_squad_blocks_switch_off(db, seeded):
    data = _report(db, seeded["squad_a"])
    spec = X.system_spec("dashboard")
    sq = _sec(spec, "squads")
    full = _text(_prs(E.render(spec, _ctx("dashboard", report=data))).slides[0])
    assert "Moral" in full and "Budget" in full
    for b in ("mood", "budget", "key_messages", "legend", "stamp", "status_legend"):
        sq["blocks"][b]["enabled"] = False
    txt = _text(_prs(E.render(spec, _ctx("dashboard", report=data))).slides[0])
    assert "Moral" not in txt and "Budget" not in txt and "Messages" not in txt
    assert "Généré le" not in txt
    # the timeline is still there, and took the room
    assert "Q1" in txt


def test_summary_table_columns_and_kpis(db, seeded):
    data = _report(db)
    spec = X.system_spec("dashboard")
    summ = _sec(spec, "summary")
    summ["blocks"]["table"]["params"]["columns"] = ["name", "progress"]
    summ["blocks"]["kpis"]["params"]["items"] = ["squads"]
    prs = _prs(E.render(spec, _ctx("dashboard", report=data)))
    tables = [sh.table for sh in prs.slides[0].shapes if getattr(sh, "has_table", False) and sh.has_table]
    assert len(tables) == 1 and len(tables[0].columns) == 2
    assert "Bloqués" not in _text(prs.slides[0]).split("\n")[0:8]


def test_sections_reorder_filter_and_switch_off(db, seeded):
    data = _report(db)
    spec = X.system_spec("weekly")
    spec["sections"] = list(reversed(spec["sections"]))
    _sec(spec, "summary")["enabled"] = False
    _sec(spec, "squads")["params"]["filter"] = "reported"
    prs = _prs(E.render(spec, _ctx("weekly", report=data)))
    # attention first, no summary; squads filtered to those that reported (none here)
    assert "Points d'attention" in _text(prs.slides[0]) or "attention" in _text(prs.slides[0]).lower()
    assert len(prs.slides) == 1


def test_steerco_panels_switch_off(db, seeded):
    from app.routers.steerco import I18N
    rows = [{"squad_name": "P", "platform_id": 1, "data": {"kpis": [{"label": "Users", "value": "3"}],
                                                          "sla": {}, "last_events": [], "next_events": []}}]
    spec = X.system_spec("steerco")
    full = _text(_prs(E.render(spec, _ctx("steerco", steerco=(rows, f"{YEAR}-07", I18N["fr"])))).slides[0])
    sec = spec["sections"][0]
    for b in ("sla", "incidents", "last_events", "next_events"):
        sec["blocks"][b]["enabled"] = False
    txt = _text(_prs(E.render(spec, _ctx("steerco", steerco=(rows, f"{YEAR}-07", I18N["fr"])))).slides[0])
    assert "SLA" in full and "SLA" not in txt and "Users" in txt


# --------------------------------------------------------------------------
# Generic sections
# --------------------------------------------------------------------------
def test_cover_text_custom_footer_and_tokens(db, seeded):
    data = _report(db)
    spec = X.normalize({"sections": [
        {"id": "cover", "type": "cover", "params": {"title": "Comite {scope}", "subtitle": "{year}"}},
        {"id": "mot", "type": "text", "params": {"title": "Le mot du comite", "body": "# Points\n- Un\n- Deux"}},
        {"id": "grid", "type": "custom", "params": {"title": "Synthese {scope}"}, "items": [
            {"id": "t", "widget": "text", "zone": [0, 0, 6, 2], "params": {"text": "Bonjour {scope}"}},
            {"id": "k", "widget": "kpi_tiles", "zone": [0, 2, 12, 4]},
            {"id": "tb", "widget": "squad_table", "zone": [0, 4, 12, 8]}]},
        {"id": "per", "type": "custom", "params": {"repeat": "per_squad"}, "items": [
            {"id": "h", "widget": "squad_header", "zone": [0, 0, 12, 1]},
            {"id": "tl", "widget": "squad_timeline", "zone": [0, 1, 12, 8]}]},
    ], "doc": {"footer": "Interne, {scope}", "page_numbers": True}}, "dashboard")
    prs = _prs(E.render(spec, _ctx("dashboard", report=data)))
    texts = [_text(s) for s in prs.slides]
    assert "Comite Tribe One" in texts[0] and str(YEAR) in texts[0]
    assert "Le mot du comite" in texts[1] and "• Un" in texts[1]
    assert "Bonjour Tribe One" in texts[2] and "Squad A" in texts[2]
    assert any("Squad A" in t for t in texts[3:])
    n = len(prs.slides)
    # the footer skips the cover, which is not numbered either
    assert f"{n}/{n}" in texts[-1] and "Interne, Tribe One" in texts[1] and "Interne" not in texts[0]


def test_widgets_without_their_data_say_so(db, seeded):
    spec = X.normalize({"sections": [{"id": "g", "type": "custom", "items": [
        {"id": "i", "widget": "image", "zone": [0, 0, 4, 4]}]}]}, "org")
    prs = _prs(E.render(spec, _ctx("org", org=([], "T"))))
    assert "Pas de donnée" in _text(prs.slides[0])


def test_imported_slide_is_copied_with_its_fields(db, seeded):
    pptx = pytest.importorskip("pptx")
    from pptx.util import Inches
    src = pptx.Presentation()
    sl = src.slides.add_slide(src.slide_layouts[6])
    sl.shapes.add_textbox(Inches(1), Inches(1), Inches(5), Inches(1)).text_frame.text = "Contexte {scope} {year}"
    png = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")
    sl.shapes.add_picture(io.BytesIO(png), Inches(1), Inches(3), Inches(1), Inches(1))
    buf = io.BytesIO(); src.save(buf)
    spec = X.normalize({"sections": [{"id": "imp", "type": "imported", "params": {"asset": 7, "slide": 1}}]},
                       "dashboard")
    ctx = _ctx("dashboard", report=_report(db))
    ctx.asset = lambda aid: buf.getvalue() if aid == 7 else None
    out = _prs(E.render(spec, ctx))
    assert f"Contexte Tribe One {YEAR}" in _text(out.slides[0])
    assert any(sh.shape_type == 13 for sh in out.slides[0].shapes)   # the picture came along


def test_theme_colours_and_font_reach_the_deck(db, seeded):
    data = _report(db)
    ctx = _ctx("dashboard", report={**data, "doc": "dashboard"})
    ctx.theme = {"palette": {"primary": "#7A1F5C"}, "font": "Arial", "font_scale": 1.0}
    xml = "".join(_xml(E.render(X.system_spec("dashboard"), ctx)).values())
    plain = "".join(_xml(E.render(X.system_spec("dashboard"), _ctx("dashboard", report={**data, "doc": "dashboard"}))).values())
    assert "7A1F5C" in xml and "7A1F5C" not in plain
    assert xml.count("1E2761") < plain.count("1E2761")
    assert 'typeface="Arial"' in xml


# --------------------------------------------------------------------------
# Inheritance
# --------------------------------------------------------------------------
def test_diff_apply_round_trip_and_locks():
    parent = X.system_spec("weekly")
    child = X.normalize(parent, "weekly")
    _sec(child, "squads")["blocks"]["mood"]["enabled"] = False
    child["sections"].append(X.normalize_section({"id": "mot", "type": "text"}, "weekly"))
    child["sections"] = [child["sections"][-1]] + child["sections"][:-1]
    patch = X.diff(parent, child)
    assert set(patch) >= {"sections", "added", "order"}
    again, skipped = X.apply(parent, patch)
    assert again == child and skipped == []
    # the parent locks its squad section and forbids additions
    locked, skipped = X.apply(parent, patch, ["section/squads", "add"])
    assert _sec(locked, "squads")["blocks"]["mood"]["enabled"] is True
    assert {s["path"] for s in skipped} >= {"section/squads", "section/mot"}
    # a change to a section the parent dropped is kept aside, not applied
    gone = X.normalize({"sections": [s for s in parent["sections"] if s["id"] != "squads"]}, "weekly")
    _eff, skipped = X.apply(gone, patch)
    assert {"path": "section/squads", "reason": "orphan"} in skipped


def test_banned_characters_never_reach_a_template():
    spec = X.normalize({"sections": [{"type": "text", "params": {
        "title": "A" + chr(0x2014) + "B", "body": "x" + chr(0xB7) + "y"}}]}, "dashboard")
    assert spec["sections"][0]["params"]["title"] == "A,B"
    assert spec["sections"][0]["params"]["body"] == "x,y"


# --------------------------------------------------------------------------
# The API: rights, publishing, assignment, preview
# --------------------------------------------------------------------------
def _create(client, **kw):
    r = client.post("/api/exports/templates", json=kw)
    assert r.status_code == 201, r.text
    return r.json()


def test_tribe_template_published_and_assigned_drives_the_export(client, db, seeded):
    login(client, seeded["tribe"])
    t = _create(client, doc_kind="dashboard", name="Comite T1", scope_type="tribe", scope_id=seeded["t1"])
    assert t["mode"] == "derived"
    d = client.get(f"/api/exports/templates/{t['id']}").json()
    spec = d["spec"]
    _sec(spec, "squads")["blocks"]["mood"]["enabled"] = False
    spec["sections"].insert(0, {"id": "cover", "type": "cover", "params": {"title": "Comite {scope}"}})
    r = client.put(f"/api/exports/templates/{t['id']}", json={"spec": spec, "locks": ["section/squads"]})
    assert r.status_code == 200, r.text
    # not published yet: assigning is refused, the export is unchanged
    r = client.put("/api/exports/assignments", json={"doc_kind": "dashboard", "scope_type": "tribe",
                                                     "scope_id": seeded["t1"], "template_id": t["id"]})
    assert r.status_code == 409
    assert client.post(f"/api/exports/templates/{t['id']}/publish", json={"comment": "v1"}).status_code == 200
    r = client.put("/api/exports/assignments", json={"doc_kind": "dashboard", "scope_type": "tribe",
                                                     "scope_id": seeded["t1"], "template_id": t["id"]})
    assert r.status_code == 200
    r = client.get("/api/reports/dashboard.pptx")
    prs = _prs(r.content)
    assert "Comite" in _text(prs.slides[0])
    assert all("Moral" not in _text(s) for s in list(prs.slides)[1:])
    assert "Comite" in r.headers["content-disposition"] or ".pptx" in r.headers["content-disposition"]
    # the compare endpoint says what changed against the parent
    ch = client.get(f"/api/exports/templates/{t['id']}/compare", params={"a": "parent", "b": "published"}).json()
    paths = {c["path"] for c in ch["changes"]}
    assert "section/cover" in paths and "section/squads/block/mood" in paths


def _open_studio_to_squad_leaders(db):
    """The Studio is closed to squad leaders by default (Admin > Personas)."""
    from app.personasconfig import get_personas, set_personas
    personas = get_personas(db)
    for p in personas:
        if p["key"] == "squad_leader":
            p["caps"]["exports"] = True
    set_personas(db, personas)
    db.commit()


def test_studio_defaults_to_admin_and_tribe_leader(db, seeded):
    from app.personasconfig import get_personas
    on = {p["key"] for p in get_personas(db) if p["caps"]["exports"]}
    assert on == {"admin", "tribe_leader"}


def test_squad_leader_designs_in_simple_mode_only(client, db, seeded):
    _open_studio_to_squad_leaders(db)
    login(client, seeded["sl_a"])
    t = _create(client, doc_kind="dashboard", name="Ma squad", scope_type="squad", scope_id=seeded["squad_a"],
                mode="root")
    assert t["mode"] == "derived" and t["simple_only"]
    spec = client.get(f"/api/exports/templates/{t['id']}").json()["spec"]
    _sec(spec, "squads")["blocks"]["budget"]["enabled"] = False
    assert client.put(f"/api/exports/templates/{t['id']}", json={"spec": spec}).status_code == 200
    spec["sections"].append({"id": "mot", "type": "text"})
    assert client.put(f"/api/exports/templates/{t['id']}", json={"spec": spec}).status_code == 403
    # not on another squad, not on the tribe
    r = client.post("/api/exports/templates", json={"doc_kind": "dashboard", "name": "x", "scope_type": "squad",
                                                    "scope_id": seeded["squad_b"]})
    assert r.status_code == 403
    r = client.post("/api/exports/templates", json={"doc_kind": "dashboard", "name": "x", "scope_type": "tribe",
                                                    "scope_id": seeded["t1"]})
    assert r.status_code == 403


def test_a_member_designs_nothing_and_a_tribe_leader_not_the_organisation(client, db, seeded):
    login(client, seeded["member"])
    r = client.post("/api/exports/templates", json={"doc_kind": "dashboard", "name": "x", "scope_type": "tribe",
                                                    "scope_id": seeded["t1"]})
    assert r.status_code == 403
    # the member persona does not open the Studio at all
    assert client.get("/api/exports/catalog").status_code == 403
    client.post("/api/auth/logout")
    login(client, seeded["tribe"])
    r = client.put("/api/exports/assignments", json={"doc_kind": "dashboard", "scope_type": "global",
                                                     "template_id": None})
    assert r.status_code == 403
    r = client.post("/api/exports/templates", json={"doc_kind": "dashboard", "name": "x", "scope_type": "tribe",
                                                    "scope_id": seeded["t2"]})
    assert r.status_code == 403


def test_standard_cannot_be_edited(client, db, seeded):
    login(client, seeded["admin"])
    std = next(t for t in client.get("/api/exports/templates", params={"doc_kind": "weekly"}).json() if t["system"])
    assert client.put(f"/api/exports/templates/{std['id']}", json={"name": "x"}).status_code == 409
    assert client.delete(f"/api/exports/templates/{std['id']}").status_code == 409


def test_parent_lock_beats_the_child(client, db, seeded):
    login(client, seeded["admin"])
    g = _create(client, doc_kind="dashboard", name="Groupe", scope_type="global")
    spec = client.get(f"/api/exports/templates/{g['id']}").json()["spec"]
    client.put(f"/api/exports/templates/{g['id']}", json={"spec": spec, "locks": ["section/squads"]})
    client.post(f"/api/exports/templates/{g['id']}/publish", json={})
    c = _create(client, doc_kind="dashboard", name="T1", scope_type="tribe", scope_id=seeded["t1"],
                from_template_id=g["id"])
    cspec = client.get(f"/api/exports/templates/{c['id']}").json()["spec"]
    _sec(cspec, "squads")["blocks"]["mood"]["enabled"] = False
    d = client.put(f"/api/exports/templates/{c['id']}", json={"spec": cspec}).json()
    assert "section/squads" in d["inherited_locks"]
    assert _sec(d["spec"], "squads")["blocks"]["mood"]["enabled"] is True
    assert any(s["reason"] == "locked" for s in d["skipped"])
    # a derived parent cannot be deleted
    assert client.delete(f"/api/exports/templates/{g['id']}").status_code == 409


def test_preview_is_drawn_from_the_deck_with_its_checks(client, db, seeded):
    login(client, seeded["admin"])
    spec = X.system_spec("dashboard")
    spec["sections"].append({"id": "mot", "type": "text", "enabled": True, "params": {
        "title": "Note", "body": "x"}, "blocks": {}})
    spec["sections"].append({"id": "g", "type": "custom", "enabled": True,
                             "params": {"title": "", "repeat": "once", "filter": "all"}, "blocks": {},
                             "items": [{"id": "t", "widget": "text", "zone": [0, 0, 1, 1],
                                        "params": {"text": "Un texte beaucoup trop long pour une case aussi petite " * 4,
                                                   "size": 6, "color": "#FFFFFF", "fill": "#FFFFFF"}}]})
    r = client.post("/api/exports/preview", json={"doc_kind": "dashboard", "spec": spec,
                                                  "context": {"tribe_id": seeded["t1"]}})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["slides"] == body["html"].count('class="slide"') and body["slides"] >= 3
    kinds = {lint["kind"] for lint in body["lints"]}
    assert {"overflow", "contrast"} <= kinds



def test_the_preview_flags_small_text_and_banned_characters():
    pptx = pytest.importorskip("pptx")
    from pptx.util import Inches, Pt
    from app import pptxhtml
    prs = pptx.Presentation()
    s = prs.slides.add_slide(prs.slide_layouts[6])
    tf = s.shapes.add_textbox(Inches(1), Inches(1), Inches(4), Inches(1)).text_frame
    r = tf.paragraphs[0].add_run(); r.text = "Minuscule"; r.font.size = Pt(6)
    tf2 = s.shapes.add_textbox(Inches(1), Inches(3), Inches(4), Inches(1)).text_frame
    tf2.text = "A" + chr(0x2014) + "B"
    html, lints, n = pptxhtml.render(prs)
    kinds = {lint["kind"] for lint in lints}
    assert n == 1 and {"small_text", "banned_char"} <= kinds
    assert "Minuscule" in html


def test_preview_keeps_the_export_gates(client, db, seeded):
    from app.modulesconfig import set_modules
    set_modules(db, {"steerco": {"enabled": False}})
    db.commit()
    login(client, seeded["admin"])
    r = client.post("/api/exports/preview", json={"doc_kind": "steerco", "context": {"period": f"{YEAR}-07"}})
    assert r.status_code == 404


def test_one_off_render_and_html_slides(client, db, seeded):
    _open_studio_to_squad_leaders(db)
    login(client, seeded["sl_a"])
    spec = X.system_spec("dashboard")
    _sec(spec, "summary")["enabled"] = False
    r = client.post("/api/exports/render", json={"doc_kind": "dashboard", "spec": spec,
                                                 "context": {"squad_id": seeded["squad_a"]}})
    assert r.status_code == 200 and r.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.presentationml")
    assert len(_prs(r.content).slides) == 1
    r = client.get("/api/exports/document.html", params={"doc_kind": "dashboard", "squad_id": seeded["squad_a"]})
    assert r.status_code == 200 and '<section class="slide"' in r.text


def test_assets_are_checked_by_their_content(client, db, seeded):
    login(client, seeded["admin"])
    r = client.post("/api/exports/assets", files={"file": ("logo.png", b"not an image", "image/png")})
    assert r.status_code == 422
    png = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")
    r = client.post("/api/exports/assets", files={"file": ("x.txt", png, "text/plain")})
    assert r.status_code == 201 and r.json()["kind"] == "image" and r.json()["mime"] == "image/png"
    # a macro-enabled deck is refused
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("ppt/presentation.xml", "<x/>")
        z.writestr("ppt/vbaProject.bin", b"x")
    r = client.post("/api/exports/assets", files={"file": ("m.pptx", buf.getvalue(), "application/octet-stream")})
    assert r.status_code == 422


def test_template_file_round_trip(client, db, seeded):
    login(client, seeded["admin"])
    th = client.post("/api/exports/themes", json={"name": "Charte", "config": {
        "palette": {"primary": "#123456", "bogus": "#000000"}, "font": "Comic", "font_scale": 9}}).json()
    assert th["config"] == {"palette": {"primary": "#123456"}, "font": "", "font_scale": 1.5}
    t = _create(client, doc_kind="roadmap", name="Export", scope_type="global", mode="detached")
    spec = client.get(f"/api/exports/templates/{t['id']}").json()["spec"]
    spec["theme_id"] = th["id"]
    client.put(f"/api/exports/templates/{t['id']}", json={"spec": spec})
    client.post(f"/api/exports/templates/{t['id']}/publish", json={})
    f = client.get(f"/api/exports/templates/{t['id']}/file").json()
    assert f["format"] == "teamfollowup-export-template" and f["theme"]["config"]["palette"]["primary"] == "#123456"
    r = client.post("/api/exports/templates/import", json={"scope_type": "tribe", "scope_id": seeded["t1"], "file": f})
    assert r.status_code == 201, r.text
    d = client.get(f"/api/exports/templates/{r.json()['id']}").json()
    assert d["spec"]["theme_id"] and d["spec"]["theme_id"] != th["id"]


def test_a_tribe_document_can_use_each_squad_s_own_slide(client, db, seeded):
    login(client, seeded["admin"])
    sq = _create(client, doc_kind="dashboard", name="A", scope_type="squad", scope_id=seeded["squad_a"])
    spec = client.get(f"/api/exports/templates/{sq['id']}").json()["spec"]
    _sec(spec, "squads")["blocks"]["mood"]["enabled"] = False
    client.put(f"/api/exports/templates/{sq['id']}", json={"spec": spec})
    client.post(f"/api/exports/templates/{sq['id']}/publish", json={})
    client.put("/api/exports/assignments", json={"doc_kind": "dashboard", "scope_type": "squad",
                                                 "scope_id": seeded["squad_a"], "template_id": sq["id"]})
    tr = _create(client, doc_kind="dashboard", name="T", scope_type="tribe", scope_id=seeded["t1"])
    tspec = client.get(f"/api/exports/templates/{tr['id']}").json()["spec"]
    _sec(tspec, "squads")["params"]["use_squad_variant"] = True
    client.put(f"/api/exports/templates/{tr['id']}", json={"spec": tspec})
    client.post(f"/api/exports/templates/{tr['id']}/publish", json={})
    client.put("/api/exports/assignments", json={"doc_kind": "dashboard", "scope_type": "tribe",
                                                 "scope_id": seeded["t1"], "template_id": tr["id"]})
    prs = _prs(client.get("/api/reports/dashboard.pptx", params={"tribe_id": seeded["t1"]}).content)
    by_name = {}
    for s in list(prs.slides)[1:]:
        t = _text(s)
        by_name["A" if "Squad A" in t else "B"] = t
    assert "Moral" not in by_name["A"] and "Moral" in by_name["B"]


def test_automatic_mails_attach_the_layout_of_their_scope(client, db, seeded):
    """What a tribe leader sets for the weekly report is what the scheduled mail
    attaches: the tribe's layout for the tribe's report, a squad's own for its."""
    from app.exportstore import render_report
    login(client, seeded["tribe"])

    def own(scope_type, scope_id, title):
        tpl = _create(client, doc_kind="weekly", name=title, scope_type=scope_type, scope_id=scope_id)
        spec = client.get(f"/api/exports/templates/{tpl['id']}").json()["spec"]
        spec["sections"].insert(0, {"id": "cover", "type": "cover", "params": {"title": title}})
        client.put(f"/api/exports/templates/{tpl['id']}", json={"spec": spec})
        client.post(f"/api/exports/templates/{tpl['id']}/publish", json={})
        assert client.put("/api/exports/assignments", json={"doc_kind": "weekly", "scope_type": scope_type,
                                                            "scope_id": scope_id, "template_id": tpl["id"]}).status_code == 200
    own("tribe", seeded["t1"], "Mise en page tribe")
    own("squad", seeded["squad_a"], "Mise en page squad A")
    tribe_data = report_mod.build_report_data(db, seeded["t1"], YEAR, 7, lang="fr")
    assert "Mise en page tribe" in _text(_prs(render_report(db, tribe_data)).slides[0])
    for sq, title in ((seeded["squad_a"], "Mise en page squad A"), (seeded["squad_b"], "Mise en page tribe")):
        data = report_mod.build_report_data(db, None, YEAR, 7, squad_id=sq, lang="fr")
        assert title in _text(_prs(render_report(db, data)).slides[0])


def test_the_studio_opens_per_persona(client, db, seeded):
    """Admin > Personas decides who opens the Studio (capability "exports", on by
    default for tribe and squad leaders); the role still decides what they change."""
    from app.personasconfig import get_personas, set_personas
    login(client, seeded["tribe"])
    assert client.get("/api/exports/catalog").json()["designer"] is True
    personas = get_personas(db)
    for p in personas:
        if p["key"] == "tribe_leader":
            p["caps"]["exports"] = False
    set_personas(db, personas)
    db.commit()
    assert client.get("/api/exports/catalog").status_code == 403
    r = client.post("/api/exports/templates", json={"doc_kind": "dashboard", "name": "x", "scope_type": "tribe",
                                                    "scope_id": seeded["t1"]})
    assert r.status_code == 403
