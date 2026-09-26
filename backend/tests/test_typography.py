"""No em dash and no middot anywhere in the repository.

The project convention (see ``CLAUDE.md``) bans the em dash (U+2014) and the
middot (U+00B7): they read as machine-written. The rule started life scoped to
"anything a user reads", and the scope was the problem. The weekly report and the
PPTX export used the middot as their separator throughout; the API reference used
it 92 times; and 105 em dashes sat in router docstrings, which FastAPI publishes
as endpoint descriptions, so they reached Swagger UI and the committed OpenAPI
snapshot. A rule with a boundary needs someone to adjudicate the boundary every
time, and nobody does.

So the scope is now the whole repository, and this guard is a flat text scan
rather than anything clever. Two consequences worth knowing:

  * the characters are written here as ``\\u`` escapes, so this file passes its
    own check and needs no exemption. ``CLAUDE.md`` names the code points for the
    same reason. There is no allowlist, which is the point: an allowlist is where
    a rule goes to die.
  * generated artefacts are covered too (``docs/openapi.json`` is built from the
    docstrings), so a dash reintroduced in a docstring fails here as well as in
    the snapshot check.

Replacements, per ``CLAUDE.md``: a comma, a colon, parentheses, a line break, or a
plain space, whichever the sentence actually wants.
"""
from __future__ import annotations

import pathlib

BANNED = {"\u2014": "em dash", "\u00b7": "middot"}

REPO = pathlib.Path(__file__).resolve().parents[2]

# Build output, dependencies, caches and local artefacts: not ours to police.
SKIP_DIRS = {
    ".git", ".pytest_cache", "__pycache__", "node_modules", ".venv-test", ".venv",
    "dist", "static", "backups", "test-results", "playwright-report", "htmlcov",
}

# Text we author. A suffix allowlist rather than a binary sniff: the repo also
# holds .pptx templates and .png assets, and guessing at those buys nothing.
SUFFIXES = {
    ".py", ".ts", ".tsx", ".js", ".jsx", ".md", ".html", ".css", ".json",
    ".yml", ".yaml", ".sh", ".toml", ".cfg", ".ini", ".txt", ".sql", ".example",
}
NAMES = {".coveragerc", ".env.example", "Dockerfile", "docker-entrypoint.sh"}


def _files() -> list[pathlib.Path]:
    out = []
    for path in REPO.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.suffix in SUFFIXES or path.name in NAMES:
            out.append(path)
    return out


def test_no_em_dash_and_no_middot_anywhere():
    offences = []
    for path in _files():
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for n, line in enumerate(text.splitlines(), 1):
            for char, label in BANNED.items():
                if char in line:
                    rel = path.relative_to(REPO).as_posix()
                    offences.append(f"{rel}:{n}: {label} in {line.strip()[:80]!r}")
    assert offences == [], (
        f"{len(offences)} forbidden character(s). Use a comma, a colon, parentheses, a line "
        "break or a plain space (CLAUDE.md):\n" + "\n".join(offences[:40])
    )


def test_the_guard_actually_looks_at_something():
    """A scan that silently matches nothing is worse than no scan.

    The skip list and the suffix allowlist are both easy to over-tighten, and the
    failure mode is a permanently green test.
    """
    files = _files()
    assert len(files) > 100, f"only {len(files)} files scanned, the filters are too narrow"
    names = {p.name for p in files}
    for expected in ("report.py", "i18n.tsx", "CHANGELOG.md", "04-api-reference.md", "openapi.json"):
        assert expected in names, f"{expected} is not being scanned"
