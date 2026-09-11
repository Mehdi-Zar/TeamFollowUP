"""Importing an organisation from an administrator-supplied file.

This module had no tests at all, and it is the one that parses a file somebody
uploads: an Excel workbook whose columns are read BY POSITION, whose booleans are
words in two languages, and whose import is meant to be safe to re-run against a
populated environment. Every one of those properties is a promise the code makes
and nothing was checking.

The round-trip test is the important one: the template the app hands out must be
readable by the parser that receives it back. Those two functions live a hundred
lines apart and nothing tied them together.
"""
import io
from datetime import datetime

import pytest
from sqlalchemy import select

from app import import_org as mod
from app.models import Initiative, Otd, Squad, Tribe, User


def _wb_bytes(rows: dict) -> bytes:
    """Build an org workbook the way a filled template looks, from plain rows."""
    from openpyxl import Workbook
    wb = Workbook()
    wb.remove(wb.active)
    for sheet, content in rows.items():
        ws = wb.create_sheet(sheet)
        for row in content:
            ws.append(list(row))
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


HEADERS = {
    "Tribu": ["Annee", "Tribu", "Description", "Leader", "Email"],
    "Squads": ["Nom", "Type", "Leader", "Email", "Produits", "Hardware", "KPIs", "Budget"],
    "Initiatives": ["Titre", "Squad", "Owner", "Echeance", "Description"],
    "OTD": ["Titre", "Squad", "Date engagee", "Description"],
}


def _minimal_workbook(**over) -> bytes:
    rows = {
        "Tribu": [HEADERS["Tribu"], [2026, "Cloud Platform", "La tribu", "Ada L", "ada@example.com"]],
        "Squads": [HEADERS["Squads"],
                   ["Landing Zone", "product", "Bob S", "bob@example.com",
                    "LZ, Guardrails", "Rack A, Rack B", "oui", "non"],
                   ["Run", "transverse", None, None, None, None, None, None]],
        "Initiatives": [HEADERS["Initiatives"],
                        ["Migrer le socle", "Landing Zone", "Ada L", datetime(2026, 6, 30), "desc"]],
        "OTD": [HEADERS["OTD"], ["Livrer la LZ v2", "Landing Zone", datetime(2026, 9, 30), None]],
    }
    rows.update(over)
    return _wb_bytes(rows)


# ---- parsing -------------------------------------------------------------------

def test_columns_are_read_by_position_not_by_header_text():
    """The docstring promises headers can be translated freely. Hold it to that."""
    english = {
        "Tribu": [["Year", "Tribe", "Description", "Leader", "Email"],
                  [2026, "Cloud Platform", "The tribe", "Ada L", "ada@example.com"]],
    }
    data = mod.read_upload("org.xlsx", _minimal_workbook(**english))
    assert data["tribe"]["name"] == "Cloud Platform"
    assert data["tribe"]["leader"]["email"] == "ada@example.com"
    assert data["year"] == 2026


def test_comma_separated_cells_become_clean_lists():
    data = mod.read_upload("org.xlsx", _minimal_workbook())
    lz = data["squads"][0]
    assert lz["products"] == ["LZ", "Guardrails"]
    assert lz["hardware"] == ["Rack A", "Rack B"]
    # An empty cell is an empty list, never [""].
    assert data["squads"][1]["products"] == []


@pytest.mark.parametrize("cell,expected", [
    ("oui", True), ("OUI", True), ("yes", True), ("true", True), ("1", True),
    ("x", True), ("vrai", True), (" Oui ", True),
    ("non", False), ("no", False), ("", False), ("0", False), ("peut-etre", False),
])
def test_booleans_are_read_in_both_languages(cell, expected):
    assert mod._yesno(cell) is expected


def test_rows_with_an_empty_first_cell_are_dropped():
    """Excel hands back trailing empty rows for free; they must not become squads."""
    rows = {"Squads": [HEADERS["Squads"],
                       ["Landing Zone", "product", None, None, None, None, None, None],
                       [None, None, None, None, None, None, None, None],
                       ["", None, None, None, None, None, None, None]]}
    data = mod.read_upload("org.xlsx", _minimal_workbook(**rows))
    assert [s["name"] for s in data["squads"]] == ["Landing Zone"]


def test_a_short_row_does_not_raise():
    """A file saved by hand can have fewer columns than the template."""
    rows = {"Squads": [HEADERS["Squads"], ["Landing Zone"]]}
    data = mod.read_upload("org.xlsx", _minimal_workbook(**rows))
    assert data["squads"][0]["name"] == "Landing Zone"
    assert data["squads"][0]["type"] == "product"     # the default fills in
    assert data["squads"][0]["kpis_enabled"] is True


def test_a_missing_sheet_is_not_fatal():
    data = mod.read_upload("org.xlsx", _wb_bytes({
        "Tribu": [HEADERS["Tribu"], [2026, "Cloud Platform", None, None, None]]}))
    assert data["squads"] == [] and data["initiatives"] == [] and data["otds"] == []


def test_yaml_is_accepted_too():
    data = mod.read_upload("org.yaml", b"year: 2026\ntribe:\n  name: Cloud Platform\n")
    assert data["tribe"]["name"] == "Cloud Platform"


def test_an_unsupported_extension_is_refused_by_name():
    with pytest.raises(ValueError):
        mod.read_upload("org.csv", b"whatever")
    with pytest.raises(ValueError):
        mod.read_upload("", b"whatever")


def test_the_template_the_app_hands_out_can_be_read_back():
    """The two ends of the same round trip, a hundred lines apart in the module."""
    data = mod.read_upload("template.xlsx", mod.template_bytes())
    assert set(data) >= {"year", "tribe", "squads", "initiatives", "otds"}


# ---- importing -----------------------------------------------------------------

def test_import_creates_the_whole_organisation(db):
    data = mod.read_upload("org.xlsx", _minimal_workbook())
    summary = mod.import_org(db, data)

    assert summary["tribe"] == "Cloud Platform"
    assert summary["year"] == 2026
    assert summary["squads"] == 2
    assert summary["created"]["squads"] == 2

    tribe = db.scalar(select(Tribe).where(Tribe.name == "Cloud Platform"))
    assert tribe is not None
    squads = db.scalars(select(Squad).where(Squad.tribe_id == tribe.id)).all()
    assert {s.name for s in squads} == {"Landing Zone", "Run"}
    lz = next(s for s in squads if s.name == "Landing Zone")
    assert lz.products == ["LZ", "Guardrails"]
    assert lz.kpis_enabled is True and lz.budget_enabled is False
    assert lz.squad_type == "product"

    assert db.scalar(select(Initiative).where(Initiative.title == "Migrer le socle")) is not None
    assert db.scalar(select(Otd).where(Otd.title == "Livrer la LZ v2")) is not None


def test_leaders_are_created_with_the_right_roles(db):
    mod.import_org(db, mod.read_upload("org.xlsx", _minimal_workbook()))
    ada = db.scalar(select(User).where(User.email == "ada@example.com"))
    bob = db.scalar(select(User).where(User.email == "bob@example.com"))
    assert ada.role == "tribe_leader"
    assert bob.role == "squad_leader"
    # Created active, so a later IdP login inherits the account instead of queuing.
    assert ada.status == "active"


def test_reimporting_the_same_file_changes_nothing(db):
    """Idempotent by natural key is the promise that makes this safe to re-run."""
    data = mod.read_upload("org.xlsx", _minimal_workbook())
    first = mod.import_org(db, data)
    second = mod.import_org(db, mod.read_upload("org.xlsx", _minimal_workbook()))

    assert first["created"]["squads"] == 2
    assert second["created"] == {"users": 0, "squads": 0, "initiatives": 0, "otds": 0}
    tribe = db.scalar(select(Tribe).where(Tribe.name == "Cloud Platform"))
    assert len(db.scalars(select(Squad).where(Squad.tribe_id == tribe.id)).all()) == 2
    assert len(db.scalars(select(User)).all()) == 2


def test_reimporting_an_edited_file_updates_in_place(db):
    mod.import_org(db, mod.read_upload("org.xlsx", _minimal_workbook()))
    edited = {"Squads": [HEADERS["Squads"],
                         ["Landing Zone", "product", "Bob S", "bob@example.com",
                          "LZ v2", "Rack C", "non", "oui"],
                         ["Run", "transverse", None, None, None, None, None, None]]}
    mod.import_org(db, mod.read_upload("org.xlsx", _minimal_workbook(**edited)))

    lz = db.scalar(select(Squad).where(Squad.name == "Landing Zone"))
    assert lz.products == ["LZ v2"]
    assert lz.hardware == ["Rack C"]
    assert lz.kpis_enabled is False and lz.budget_enabled is True
    # Still one squad, not a duplicate.
    assert len(db.scalars(select(Squad).where(Squad.name == "Landing Zone")).all()) == 1


def test_an_otd_owner_is_the_referenced_squads_leader(db):
    mod.import_org(db, mod.read_upload("org.xlsx", _minimal_workbook()))
    otd = db.scalar(select(Otd).where(Otd.title == "Livrer la LZ v2"))
    bob = db.scalar(select(User).where(User.email == "bob@example.com"))
    assert otd.owner_user_id == bob.id


def test_an_otd_finds_a_squad_the_file_does_not_restate(db):
    """The Squads sheet creates squads; it is not a condition for naming one.

    A file that only carries an OTD for a squad already in the app used to import
    an OTD owned by nobody, invisible in that squad's panel (which shows an OTD
    committed on its leader or covering one of its milestones). The import
    reported success and the screen stayed empty.
    """
    mod.import_org(db, mod.read_upload("org.xlsx", _minimal_workbook()))
    bob = db.scalar(select(User).where(User.email == "bob@example.com"))

    # Second file: same tribe, Squads sheet left empty, one more OTD on that squad.
    rows = {"Squads": [HEADERS["Squads"]],
            "Initiatives": [HEADERS["Initiatives"], ["Suite du socle", "Landing Zone", None, None, None]],
            "OTD": [HEADERS["OTD"], ["Livrer la LZ v3", "Landing Zone", datetime(2026, 11, 30), None]]}
    mod.import_org(db, mod.read_upload("org.xlsx", _minimal_workbook(**rows)))

    otd = db.scalar(select(Otd).where(Otd.title == "Livrer la LZ v3"))
    assert otd.owner_user_id == bob.id
    lz = db.scalar(select(Squad).where(Squad.name == "Landing Zone"))
    init = db.scalar(select(Initiative).where(Initiative.title == "Suite du socle"))
    assert init.squad_id == lz.id
    # The squad itself is untouched by a file that does not describe it.
    assert lz.products == ["LZ", "Guardrails"] and lz.kpis_enabled is True


def test_an_initiative_pointing_at_an_unknown_squad_stays_tribe_level(db):
    rows = {"Initiatives": [HEADERS["Initiatives"],
                            ["Sans squad", "Squad Fantome", None, None, None]]}
    mod.import_org(db, mod.read_upload("org.xlsx", _minimal_workbook(**rows)))
    init = db.scalar(select(Initiative).where(Initiative.title == "Sans squad"))
    assert init is not None and init.squad_id is None


def test_an_unknown_squad_name_is_reported_not_swallowed(db):
    """The counts alone told the administrator nothing had gone wrong.

    An OTD naming a squad that does not exist is imported without an owner, and
    an OTD without an owner appears in no screen at all. The import still says
    "1 OTD" and looks like a success. One mistyped cell was enough to lose a
    commitment silently, which is exactly how a real file was lost.
    """
    rows = {"OTD": [HEADERS["OTD"], ["Livrer la LZ v2", "Justine Cuenot", datetime(2026, 9, 30), None]]}
    summary = mod.import_org(db, mod.read_upload("org.xlsx", _minimal_workbook(**rows)))

    assert summary["otds"] == 1
    assert any("Justine Cuenot" in w for w in summary["warnings"])
    otd = db.scalar(select(Otd).where(Otd.title == "Livrer la LZ v2"))
    assert otd is not None and otd.owner_user_id is None


def test_a_title_repeated_in_the_file_is_reported(db):
    """Same tribe, same year, same title is one row: the second updates the first."""
    rows = {"OTD": [HEADERS["OTD"],
                    ["Livrer la LZ v2", "Landing Zone", datetime(2026, 9, 30), None],
                    ["Livrer la LZ v2", "Landing Zone", datetime(2026, 9, 30), None]]}
    summary = mod.import_org(db, mod.read_upload("org.xlsx", _minimal_workbook(**rows)))

    assert any("Livrer la LZ v2" in w and "plusieurs fois" in w for w in summary["warnings"])
    assert len(db.scalars(select(Otd).where(Otd.title == "Livrer la LZ v2")).all()) == 1


def test_a_clean_file_reports_no_warning(db):
    assert mod.import_org(db, mod.read_upload("org.xlsx", _minimal_workbook()))["warnings"] == []


def test_an_administrator_named_as_a_squad_leader_stays_an_administrator(db, seeded):
    """The import is reached from the admin section; it must not close the door.

    Naming an account as a squad leader used to set its role to squad_leader,
    admin included. The person running the import could lose the admin section
    with their own file, on the row describing their own squad.
    """
    rows = {"Squads": [HEADERS["Squads"],
                       ["Landing Zone", "product", "Admin", "admin@test", None, None, "oui", "non"]]}
    mod.import_org(db, mod.read_upload("org.xlsx", _minimal_workbook(**rows)))

    admin = db.scalar(select(User).where(User.email == "admin@test"))
    assert admin.role == "admin"
    # The squad still points at them: leading a squad and administering coexist.
    lz = db.scalar(select(Squad).where(Squad.name == "Landing Zone"))
    assert lz.leader_user_id == admin.id


def test_a_squad_leader_named_in_the_file_is_still_promoted(db, seeded):
    """The guard above is about admins only, not about every existing account."""
    rows = {"Squads": [HEADERS["Squads"],
                       ["Landing Zone", "product", "Member", "member@test", None, None, "oui", "non"]]}
    mod.import_org(db, mod.read_upload("org.xlsx", _minimal_workbook(**rows)))
    assert db.scalar(select(User).where(User.email == "member@test")).role == "squad_leader"


def test_nothing_outside_the_described_org_is_touched(db, seeded):
    """The docstring says so; a wipe disguised as an import would be a very bad day."""
    before = {t.name for t in db.scalars(select(Tribe)).all()}
    mod.import_org(db, mod.read_upload("org.xlsx", _minimal_workbook()))
    after = {t.name for t in db.scalars(select(Tribe)).all()}
    assert before <= after
    assert "Cloud Platform" in after


def test_the_year_defaults_to_the_current_one_when_absent(db):
    rows = {"Tribu": [HEADERS["Tribu"], [None, "Cloud Platform", None, None, None]]}
    summary = mod.import_org(db, mod.read_upload("org.xlsx", _minimal_workbook(**rows)))
    assert summary["year"] == datetime.now().year


def test_a_file_without_a_tribe_name_says_so_instead_of_crashing(db):
    """The administrator uploaded a file; the message must be about that file."""
    rows = {"Tribu": [HEADERS["Tribu"], [2026, None, "desc", None, None]]}
    with pytest.raises(ValueError, match="nom"):
        mod.import_org(db, mod.read_upload("org.xlsx", _minimal_workbook(**rows)))
