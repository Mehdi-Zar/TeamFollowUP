"""No em dash and no middot in anything a user reads.

The project convention (see ``CLAUDE.md``) bans ``—`` and ``·`` from UI labels,
FR/EN translations, generated HTML/PPTX documents, emails, titles and tooltips:
they read as machine-written. The rule was being broken where it matters most,
in the weekly report and the PPTX export, which used ``·`` as a separator
throughout, so this guard exists to keep the fix from rotting.

It inspects **string literals only**, and skips docstrings. Developer prose is
not the target: a docstring explaining a design decision may punctuate itself
however it likes, and hundreds of router docstrings do. What must stay clean is
what leaves the process and lands in front of somebody.
"""
from __future__ import annotations

import ast
import pathlib

BANNED = {"—": "em dash", "·": "middot"}

APP = pathlib.Path(__file__).resolve().parent.parent / "app"


def _docstring_nodes(tree: ast.AST) -> set[int]:
    """Ids of the Constant nodes that are docstrings, which are exempt."""
    out: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        body = getattr(node, "body", None)
        if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                and isinstance(body[0].value.value, str):
            out.add(id(body[0].value))
    return out


def _offences(path: pathlib.Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    skip = _docstring_nodes(tree)
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        if id(node) in skip:
            continue
        for char, name in BANNED.items():
            if char in node.value:
                found.append(f"{path.name}:{node.lineno}: {name} in {node.value.strip()[:70]!r}")
    return found


def test_no_em_dash_or_middot_in_any_user_facing_string():
    offences = [o for p in sorted(APP.rglob("*.py")) for o in _offences(p)]
    assert offences == [], "Forbidden typography in user-facing strings:\n" + "\n".join(offences)
