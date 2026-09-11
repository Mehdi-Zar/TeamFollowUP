"""Steerco: platform snapshots, 12-month aggregation, backfill, lang-aware one-pager.

The reporting unit is the platform, not the squad, because the committee wants one
slide per platform and a platform can be fed by several squads. The tests that
matter most here are the multi-contributor ones: two squad leaders filling the same
slide must never overwrite each other, and every figure must have an owner.
"""
from app.models import Platform, SteercoEntry
from app.platforms import default_template
from app.routers.steerco import (I18N, _aggregate, month_keys, _onepager,
                                 _render_pptx, _svg_line_chart)
from tests.conftest import login


def _enable(client):
    """Steerco module is off by default; turn it on as admin."""
    login(client, "admin@test")
    r = client.put("/api/admin/modules-config", json={"steerco": {"enabled": True}})
    assert r.status_code == 200, r.text


def _platform(db, seeded, name="TP-S3NS", squads=("squad_a",), template=None) -> int:
    """A platform fed by the named seeded squads, owning the standard slide."""
    ids = [seeded[s] for s in squads]
    from app.models import Squad
    p = Platform(tribe_id=seeded["t1"], name=name, display_order=1, steerco_enabled=True,
                 template=template or default_template(ids[0]))
    p.contributors = [db.get(Squad, i) for i in ids]
    db.add(p)
    db.flush()
    for s in p.contributors:
        s.steerco_enabled = True
    db.commit()
    return p.id


# ---- pure helpers --------------------------------------------------------------

def test_month_keys():
    assert month_keys("2026-02", 3) == ["2025-12", "2026-01", "2026-02"]
    assert len(month_keys("2026-07", 12)) == 12


def test_svg_handles_gaps_and_empty():
    svg = _svg_line_chart({"labels": ["a", "b", "c"], "y_max": 100,
                           "series": [{"name": "x", "color": "#000", "data": [None, 40, 50]}]}, "no data")
    assert svg.startswith("<svg") and "<path" in svg and "<circle" not in svg   # line only, no markers
    assert "no data" in _svg_line_chart({"series": []}, "no data")


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
    html = _onepager("TP-S3NS", "2026-07", rd, I18N["en"])
    assert "▲ +12" in html and "b-ko" in html and "b-warn" in html


def test_sla_percentages_are_capped_at_100(client, db, seeded):
    """A SLA is a percentage: 100 is the ceiling, whatever is sent (typo, import)."""
    _enable(client)
    pid = _platform(db, seeded, template={
        "kpis": [], "sla": [{"label": "A", "owner_squad_id": seeded["squad_a"]},
                            {"label": "B", "owner_squad_id": seeded["squad_a"]}],
        "incidents": {"owner_squad_id": seeded["squad_a"]}})
    login(client, seeded["sl_a"])
    r = client.put(f"/api/steerco/platform/{pid}?period=2026-07", json={
        "sla": {"services": ["A", "B"], "cells": [{"v": "994%"}, {"v": "99,4%"}]}})
    assert r.status_code == 200, r.text
    assert [c["v"] for c in r.json()["data"]["sla"]["cells"]] == ["100%", "99,4%"]
    rd = _aggregate(db, pid, "2026-07")
    assert [c["v"] for c in rd["sla"]["rows"][0]["cells"]] == ["100%", "99,4%"]


def test_onepager_layout_and_translation(db, seeded):
    pid = _platform(db, seeded)
    db.add(SteercoEntry(platform_id=pid, period="2026-07", data={
        "kpis": [{"label": "Users", "value": "247"}],
        "sla": {"services": ["Incidents"], "cells": [{"v": "99,4%", "s": "ok"}]},
        "incidents": "13"}))
    db.commit()
    rd = _aggregate(db, pid, "2026-07")
    html_en = _onepager("TP-S3NS", "2026-07", rd, I18N["en"])
    # left column (KPIs) comes before the SLA table; right column has the KPI chart
    assert html_en.index("kpi-row") < html_en.index(">SLA")   # KPI panel before the SLA panel
    assert "hdr" in html_en and "July 2026" in html_en          # header + spelled-out month
    # SLA rows are the current month + the annual average; the chart sub shows the year.
    assert "Current month" in html_en and "Annual average" in html_en and "KPI trend" in html_en
    assert "base 100" not in html_en                            # chart plots raw values, not an index
    html_fr = _onepager("TP-S3NS", "2026-07", rd, I18N["fr"])
    assert "Mois en cours" in html_fr and "Moyenne annuelle" in html_fr and "Évolution KPI" in html_fr


# ---- platforms: declaration, contributors, template ----------------------------

def test_module_gate_blocks_when_disabled(client, seeded):
    login(client, "admin@test")
    assert client.get("/api/steerco/entries?period=2026-07").status_code == 404


def test_a_platform_groups_several_squads_into_one_slide(client, db, seeded):
    """The whole point: two squads, one platform, one page in the consolidated doc."""
    _enable(client)
    login(client, seeded["tribe"])
    r = client.post("/api/steerco/platforms", json={
        "name": "TP-S3NS", "contributor_ids": [seeded["squad_a"], seeded["squad_b"]]})
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    assert [c["name"] for c in r.json()["contributors"]] == ["Squad A", "Squad B"]
    # Several contributors: ownership is a decision, so items start unassigned rather
    # than being attributed to whoever happened to be first.
    assert r.json()["template"]["kpis"][0]["owner_squad_id"] is None

    client.put(f"/api/steerco/platform/{pid}?period=2026-07",
               json={"kpis": [{"label": "Cloud Users", "value": "12"}]})
    doc = client.get("/api/steerco/document.html?period=2026-07&lang=en")
    assert doc.status_code == 200
    assert doc.text.count("class='page'") + doc.text.count('class="page"') == 1
    assert "TP-S3NS" in doc.text and "Squad A" not in doc.text


def test_contributing_squads_get_the_steerco_flag(client, db, seeded):
    """The reporting screen shows its Steerco step from this flag, so it must follow
    platform membership by itself instead of being toggled by hand."""
    _enable(client)
    login(client, seeded["tribe"])
    sid_a, sid_b = seeded["squad_a"], seeded["squad_b"]
    r = client.post("/api/steerco/platforms", json={"name": "P", "contributor_ids": [sid_a]})
    pid = r.json()["id"]
    assert client.get(f"/api/squads/{sid_a}").json()["steerco_enabled"] is True
    assert client.get(f"/api/squads/{sid_b}").json()["steerco_enabled"] is False

    client.put(f"/api/steerco/platforms/{pid}", json={"contributor_ids": [sid_b]})
    assert client.get(f"/api/squads/{sid_a}").json()["steerco_enabled"] is False   # released
    assert client.get(f"/api/squads/{sid_b}").json()["steerco_enabled"] is True

    client.delete(f"/api/steerco/platforms/{pid}")
    assert client.get(f"/api/squads/{sid_b}").json()["steerco_enabled"] is False


def test_an_admin_creates_a_platform_without_naming_a_tribe(client, db, seeded):
    """An admin belongs to no tribe, so the tribe has to come from somewhere else.

    Taking it from the first contributing squad is what makes the admin console
    usable: the screen names the squads, which already carries the answer. Without
    it every creation from an admin account was refused as out of scope.
    """
    _enable(client)
    login(client, "admin@test")
    r = client.post("/api/steerco/platforms", json={
        "name": "TP-S3NS", "contributor_ids": [seeded["squad_a"]]})
    assert r.status_code == 201, r.text
    assert r.json()["tribe_id"] == seeded["t1"]

    # Nothing to deduce it from: say so, rather than a confusing 403.
    r = client.post("/api/steerco/platforms", json={"name": "Orpheline"})
    assert r.status_code == 400 and "tribu" in r.json()["detail"].lower()


def test_dropping_a_contributor_releases_the_items_it_owned(client, db, seeded):
    """An item owned by a squad that no longer contributes is editable by nobody and
    would silently stay empty for ever. It falls back to unassigned."""
    _enable(client)
    login(client, seeded["tribe"])
    sid_a, sid_b = seeded["squad_a"], seeded["squad_b"]
    pid = client.post("/api/steerco/platforms", json={
        "name": "P", "contributor_ids": [sid_a, sid_b],
        "template": {"kpis": [{"label": "Users", "owner_squad_id": sid_a},
                              {"label": "K8aaS", "owner_squad_id": sid_b}],
                     "sla": [{"label": "Incidents", "owner_squad_id": sid_a}],
                     "incidents": {"owner_squad_id": sid_b}}}).json()["id"]
    out = client.put(f"/api/steerco/platforms/{pid}", json={"contributor_ids": [sid_b]}).json()
    owners = [k["owner_squad_id"] for k in out["template"]["kpis"]]
    assert owners == [None, sid_b]
    assert out["template"]["sla"][0]["owner_squad_id"] is None


def test_a_squad_of_another_tribe_cannot_contribute(client, db, seeded):
    """Its figures would end up on a committee deck that is not its own."""
    _enable(client)
    login(client, "admin@test")
    r = client.post("/api/steerco/platforms", json={
        "tribe_id": seeded["t1"], "name": "P", "contributor_ids": [seeded["squad_c"]]})
    assert r.status_code == 400


def test_only_leadership_declares_platforms(client, db, seeded):
    """A squad leader fills what it was assigned; it does not hand itself a column."""
    _enable(client)
    login(client, seeded["sl_a"])
    assert client.post("/api/steerco/platforms", json={"name": "P"}).status_code == 403
    pid = _platform(db, seeded)
    assert client.put(f"/api/steerco/platforms/{pid}", json={"name": "X"}).status_code == 403
    assert client.delete(f"/api/steerco/platforms/{pid}").status_code == 403


# ---- the multi-contributor write path -------------------------------------------

def test_two_contributors_fill_one_slide_without_erasing_each_other(client, db, seeded):
    """The reason platforms exist. Each leader posts the whole form, as the UI does,
    and only the items it owns are taken from its payload."""
    _enable(client)
    sid_a, sid_b = seeded["squad_a"], seeded["squad_b"]
    pid = _platform(db, seeded, squads=("squad_a", "squad_b"), template={
        "kpis": [{"label": "Users", "owner_squad_id": sid_a},
                 {"label": "K8aaS", "owner_squad_id": sid_b}],
        "sla": [{"label": "Incidents", "owner_squad_id": sid_a},
                {"label": "Gitlab", "owner_squad_id": sid_b}],
        "incidents": {"owner_squad_id": sid_b}})

    login(client, seeded["sl_a"])
    client.put(f"/api/steerco/platform/{pid}?period=2026-07", json={
        "kpis": [{"label": "Users", "value": "247"}, {"label": "K8aaS", "value": "999"}],
        "sla": {"services": ["Incidents", "Gitlab"], "cells": [{"v": "99%"}, {"v": "1%"}]},
        "incidents": "666"})
    login(client, seeded["sl_b"])
    client.put(f"/api/steerco/platform/{pid}?period=2026-07", json={
        "kpis": [{"label": "Users", "value": "0"}, {"label": "K8aaS", "value": "8"}],
        "sla": {"services": ["Incidents", "Gitlab"], "cells": [{"v": "0%"}, {"v": "95%"}]},
        "incidents": "13"})

    login(client, seeded["tribe"])
    data = client.get(f"/api/steerco/platform/{pid}?period=2026-07").json()["data"]
    assert [k["value"] for k in data["kpis"]] == ["247", "8"]         # each kept its own
    assert [c["v"] for c in data["sla"]["cells"]] == ["99%", "95%"]
    assert data["incidents"] == "13"                                  # owned by squad B


def test_a_non_contributor_cannot_write(client, db, seeded):
    _enable(client)
    pid = _platform(db, seeded, squads=("squad_a",))
    login(client, seeded["sl_b"])
    r = client.put(f"/api/steerco/platform/{pid}?period=2026-07",
                   json={"kpis": [{"label": "Cloud Users", "value": "1"}]})
    assert r.status_code == 403


def test_leadership_fills_what_nobody_owns(client, db, seeded):
    """Unassigned items are nobody's job. The tribe leader can still fill them, else
    a half-attributed template would freeze part of the slide."""
    _enable(client)
    pid = _platform(db, seeded, template={
        "kpis": [{"label": "Users", "owner_squad_id": None}],
        "sla": [], "incidents": {"owner_squad_id": None}})
    login(client, seeded["sl_a"])
    assert client.put(f"/api/steerco/platform/{pid}?period=2026-07",
                      json={"kpis": [{"label": "Users", "value": "5"}]}).status_code == 200
    assert client.get(f"/api/steerco/platform/{pid}?period=2026-07").json()["data"]["kpis"][0]["value"] == ""

    login(client, seeded["tribe"])
    client.put(f"/api/steerco/platform/{pid}?period=2026-07",
               json={"kpis": [{"label": "Users", "value": "5"}]})
    assert client.get(f"/api/steerco/platform/{pid}?period=2026-07").json()["data"]["kpis"][0]["value"] == "5"


def test_labels_come_from_the_template_not_from_the_payload(client, db, seeded):
    """A stale form must not rename the slide's rows: the template is the authority."""
    _enable(client)
    pid = _platform(db, seeded, template={
        "kpis": [{"label": "Users", "owner_squad_id": seeded["squad_a"]}],
        "sla": [], "incidents": {"owner_squad_id": seeded["squad_a"]}})
    login(client, seeded["sl_a"])
    r = client.put(f"/api/steerco/platform/{pid}?period=2026-07",
                   json={"kpis": [{"label": "Renamed by a stale tab", "value": "3"}]})
    assert r.json()["data"]["kpis"][0] == {"label": "Users", "value": "3"}


def test_each_contributor_owns_its_own_events(client, db, seeded):
    """Events are the one shared section: everybody adds lines, nobody deletes another's."""
    _enable(client)
    sid_a, sid_b = seeded["squad_a"], seeded["squad_b"]
    pid = _platform(db, seeded, squads=("squad_a", "squad_b"), template={
        "kpis": [], "sla": [], "incidents": {"owner_squad_id": sid_a}})
    login(client, seeded["sl_a"])
    client.put(f"/api/steerco/platform/{pid}?period=2026-07",
               json={"last_events": [{"date": "01/07", "text": "Vu par A"}]})
    login(client, seeded["sl_b"])
    client.put(f"/api/steerco/platform/{pid}?period=2026-07",
               json={"last_events": [{"date": "02/07", "text": "Vu par B"}]})

    login(client, seeded["tribe"])
    events = client.get(f"/api/steerco/platform/{pid}?period=2026-07").json()["data"]["last_events"]
    assert sorted(e["text"] for e in events) == ["Vu par A", "Vu par B"]
    assert {str(e["squad_id"]) for e in events} == {str(sid_a), str(sid_b)}


def test_the_entries_list_names_who_still_owes_a_figure(client, db, seeded):
    """A slide filled by several people needs to say who is late, or the tribe leader
    chases everybody at once."""
    _enable(client)
    sid_a, sid_b = seeded["squad_a"], seeded["squad_b"]
    pid = _platform(db, seeded, squads=("squad_a", "squad_b"), template={
        "kpis": [{"label": "Users", "owner_squad_id": sid_a},
                 {"label": "K8aaS", "owner_squad_id": sid_b}],
        "sla": [], "incidents": {"owner_squad_id": sid_a}})
    login(client, seeded["sl_a"])
    client.put(f"/api/steerco/platform/{pid}?period=2026-07",
               json={"kpis": [{"label": "Users", "value": "247"}], "incidents": "3"})

    login(client, seeded["tribe"])
    row = client.get("/api/steerco/entries?period=2026-07").json()[0]
    assert row["platform_name"] == "TP-S3NS" and row["filled"] is True
    assert row["missing"] == ["Squad B"]


# ---- reporting flow --------------------------------------------------------------

def test_snapshot_backfill_history_and_document(client, db, seeded):
    _enable(client)
    pid = _platform(db, seeded)
    login(client, seeded["sl_a"])
    assert client.put(f"/api/steerco/platform/{pid}?period=2026-07", json={
        "kpis": [{"label": "Cloud Users", "value": "247"}],
        "sla": {"services": ["Incidents"], "cells": [{"v": "99,4%", "s": "ok"}]},
        "incidents": "13"}).status_code == 200
    # backfill two past months in one shot
    r = client.put(f"/api/steerco/platform/{pid}/history", json={"months": {
        "2026-06": {"kpis": [{"label": "Cloud Users", "value": "210"}], "incidents": "15"},
        "2026-05": {"kpis": [{"label": "Cloud Users", "value": "200"}], "incidents": "10"}}})
    assert r.status_code == 200 and r.json()["count"] == 2
    hist = client.get(f"/api/steerco/platform/{pid}/history?period=2026-07").json()
    assert len(hist["months"]) == 12

    # leadership one-pager, in both languages, plus the PPTX
    login(client, "admin@test")
    en = client.get(f"/api/steerco/onepager.html?platform_id={pid}&period=2026-07&lang=en")
    assert en.status_code == 200 and "KPI trend" in en.text and "247" in en.text
    fr = client.get(f"/api/steerco/onepager.html?platform_id={pid}&period=2026-07&lang=fr")
    assert "Évolution KPI" in fr.text
    assert client.get("/api/steerco/document.pptx?period=2026-07&lang=en").status_code == 200


def test_backfill_goes_through_the_same_ownership_merge(client, db, seeded):
    """Pasting a year of figures must not be a back door onto a colleague's column."""
    _enable(client)
    sid_a, sid_b = seeded["squad_a"], seeded["squad_b"]
    pid = _platform(db, seeded, squads=("squad_a", "squad_b"), template={
        "kpis": [{"label": "Users", "owner_squad_id": sid_a},
                 {"label": "K8aaS", "owner_squad_id": sid_b}],
        "sla": [], "incidents": {"owner_squad_id": sid_b}})
    login(client, seeded["sl_b"])
    client.put(f"/api/steerco/platform/{pid}/history", json={"months": {
        "2026-06": {"kpis": [{"label": "Users", "value": "1"}, {"label": "K8aaS", "value": "8"}]}}})
    login(client, seeded["tribe"])
    data = client.get(f"/api/steerco/platform/{pid}?period=2026-06").json()["data"]
    assert [k["value"] for k in data["kpis"]] == ["", "8"]


def test_entry_reports_monthly_fill_status(client, db, seeded):
    """The reporting launcher relies on filled/updated_at/updated_by to show whether
    this month's Steerco is done or still to do."""
    _enable(client)
    pid = _platform(db, seeded)
    login(client, seeded["sl_a"])
    before = client.get(f"/api/steerco/platform/{pid}?period=2026-07").json()
    assert before["filled"] is False and before["updated_at"] is None
    client.put(f"/api/steerco/platform/{pid}?period=2026-07",
               json={"kpis": [{"label": "Cloud Users", "value": "1"}]})
    after = client.get(f"/api/steerco/platform/{pid}?period=2026-07").json()
    assert after["filled"] is True and after["updated_at"] and after["updated_by"] == "SL A"


def test_preview_uses_unsaved_data_without_persisting(client, db, seeded):
    """The wizard preview renders the still-unsaved snapshot (contributor accessible)
    and must not persist it."""
    _enable(client)
    pid = _platform(db, seeded)
    login(client, seeded["sl_a"])
    r = client.post(f"/api/steerco/platform/{pid}/preview.html?period=2026-07&lang=en",
                    json={"kpis": [{"label": "Users", "value": "997"}],
                          "sla": {"services": ["Incidents"], "cells": [{"v": "99,4%", "s": "ok"}]},
                          "incidents": "3"})
    assert r.status_code == 200 and "997" in r.text          # unsaved value shows in the preview
    assert client.get(f"/api/steerco/platform/{pid}?period=2026-07").json()["filled"] is False


def test_backfill_requires_edit_rights(client, db, seeded):
    _enable(client)
    pid = _platform(db, seeded)
    login(client, seeded["member"])
    assert client.put(f"/api/steerco/platform/{pid}/history",
                      json={"months": {"2026-06": {"incidents": "3"}}}).status_code in (403, 404)


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

    pid = _platform(db, seeded, name="TP-S3NS")
    login(client, "admin@test")
    r = client.get("/api/admin/import-steerco/template")
    assert r.status_code == 200 and r.content[:2] == b"PK"        # a real .xlsx (zip)

    # fill it: platform name + a couple of months of one KPI + current SLA + an event.
    # Columns are the calendar year: B = Jan ... G = Jun, H = Jul (the report month).
    wb = load_workbook(io.BytesIO(template_bytes("2026-07")))
    wb["Infos"]["B2"] = "TP-S3NS"; wb["Infos"]["B3"] = "2026-07"
    wb["KPIs"]["G2"] = 118; wb["KPIs"]["H2"] = 120          # Cloud Users Jun, Jul (current)
    wb["SLA"]["H2"] = 99.2                                   # Incidents, current month
    wb["Incidents"]["H2"] = 4
    wb["Evenements passes"]["A2"] = "12/07"; wb["Evenements passes"]["C2"] = "Incident majeur"
    wb["Evenements passes"]["D2"] = "Attention"
    buf = io.BytesIO(); wb.save(buf); buf.seek(0)

    r = client.post("/api/admin/import-steerco",
                    files={"file": ("steerco.xlsx", buf.getvalue(),
                                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
    assert r.status_code == 200, r.text
    s = r.json()
    assert s["platform"] == "TP-S3NS" and s["period"] == "2026-07" and s["months"] >= 2

    # persisted + feeds the one-pager
    rd = _aggregate(db, pid, "2026-07")
    assert rd["kpis"][0]["value"] == "120"
    assert rd["sla"]["rows"][0]["cells"][0]["s"] == "ok"       # 99,2% -> green, computed
    seen = [v for v in rd["kpi_chart"]["series"][0]["data"] if v is not None]
    assert seen == [118, 120]                               # RAW Jun + Jul values (Cloud Users)
    # The imported event's severity reaches the one-pager as a coloured chip.
    html = _onepager("TP-S3NS", "2026-07", rd, I18N["fr"])
    assert "Incident majeur" in html and "#FBF0D9" in html   # "Attention" -> amber chip


def test_an_old_workbook_saying_squad_still_imports(client, seeded, db):
    """Files already in circulation carry a "Squad" label; they must keep working."""
    import io
    from openpyxl import load_workbook
    from app.steerco_import import template_bytes

    _platform(db, seeded, name="TP-S3NS")
    wb = load_workbook(io.BytesIO(template_bytes("2026-07")))
    wb["Infos"]["A2"] = "Squad (nom exact dans l'app)"
    wb["Infos"]["B2"] = "TP-S3NS"; wb["Infos"]["B3"] = "2026-07"
    wb["KPIs"]["H2"] = 7
    buf = io.BytesIO(); wb.save(buf)

    login(client, "admin@test")
    r = client.post("/api/admin/import-steerco",
                    files={"file": ("s.xlsx", buf.getvalue(), "application/octet-stream")})
    assert r.status_code == 200, r.text


def test_template_matches_what_the_platform_reports(client, db, seeded):
    """A platform's workbook must propose ITS rows (name pre-filled, its KPI / SLA
    lines from the slide template), not a canned list."""
    import io
    from openpyxl import load_workbook

    sid = seeded["squad_a"]
    pid = _platform(db, seeded, name="TP-S3NS", template={
        "kpis": [{"label": "Cloud Users", "owner_squad_id": sid},
                 {"label": "Terraform", "owner_squad_id": sid}],
        "sla": [{"label": "Incidents", "owner_squad_id": sid},
                {"label": "Vault", "owner_squad_id": sid}],
        "incidents": {"owner_squad_id": sid}})

    login(client, "admin@test")
    r = client.get(f"/api/admin/import-steerco/template?platform_id={pid}")
    assert r.status_code == 200
    wb = load_workbook(io.BytesIO(r.content))
    assert wb["Infos"]["B2"].value == "TP-S3NS"                       # name pre-filled
    assert [wb["KPIs"].cell(i, 1).value for i in (2, 3)] == ["Cloud Users", "Terraform"]
    assert [wb["SLA"].cell(i, 1).value for i in (2, 3)] == ["Incidents", "Vault"]
    # without a platform, the standard structure is still served
    generic = load_workbook(io.BytesIO(client.get("/api/admin/import-steerco/template").content))
    assert generic["KPIs"]["A2"].value == "Cloud Users" and not generic["Infos"]["B2"].value


def test_import_never_deletes_what_was_entered_in_the_app(client, db, seeded):
    """The workbook adds and updates; it must not wipe a KPI, an SLA service or the
    events entered in the app just because the file does not mention them."""
    import io
    from openpyxl import load_workbook
    from app.steerco_import import template_bytes

    pid = _platform(db, seeded, name="TP-S3NS")
    db.add(SteercoEntry(platform_id=pid, period="2026-07", data={
        "kpis": [{"label": "Cloud Users", "value": "247"}, {"label": "Terraform", "value": "42"}],
        "sla": {"services": ["Vault"], "cells": [{"v": "95,0%"}]},
        "last_events": [{"date": "01/07", "text": "Saisi dans l'app"}]}))
    db.commit()

    # the generic template knows nothing about Terraform, Vault or the event.
    # Calendar-year columns: July (the report month) is column 8 (H).
    wb = load_workbook(io.BytesIO(template_bytes("2026-07")))
    wb["Infos"]["B2"] = "TP-S3NS"; wb["Infos"]["B3"] = "2026-07"
    wb["KPIs"].cell(2, 8, 250)                       # updates Cloud Users only (July column)
    wb["KPIs"]["A7"] = "Nouveau KPI"; wb["KPIs"].cell(7, 8, 5)      # a row added by hand
    buf = io.BytesIO(); wb.save(buf)

    login(client, "admin@test")
    r = client.post("/api/admin/import-steerco",
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


def test_import_rejects_a_malformed_report_month(seeded):
    """The report month drives the 12 collected columns, so a non "AAAA-MM" value must
    fail loudly instead of silently importing into the wrong months."""
    import io
    import pytest
    from openpyxl import load_workbook
    from app.steerco_import import parse_workbook, template_bytes

    wb = load_workbook(io.BytesIO(template_bytes("2026-07")))
    wb["Infos"]["B2"] = "TP-S3NS"; wb["Infos"]["B3"] = "juillet 2026"
    buf = io.BytesIO(); wb.save(buf)
    with pytest.raises(ValueError, match="AAAA-MM"):
        parse_workbook(buf.getvalue())


def test_import_unknown_platform_is_rejected(client, seeded):
    import io
    from openpyxl import load_workbook
    from app.steerco_import import template_bytes

    login(client, "admin@test")
    wb = load_workbook(io.BytesIO(template_bytes()))
    wb["Infos"]["B2"] = "No Such Platform"; wb["Infos"]["B3"] = "2026-07"
    buf = io.BytesIO(); wb.save(buf)
    r = client.post("/api/admin/import-steerco",
                    files={"file": ("s.xlsx", buf.getvalue(), "application/octet-stream")})
    assert r.status_code == 400 and "introuvable" in r.json()["detail"].lower()
