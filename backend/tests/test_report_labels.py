"""Les libelles des documents et le code qui les rend doivent s'accorder.

Le frontend a ce garde-fou depuis longtemps (``i18n.usage.test.ts``) et il a servi
plusieurs fois: une etiquette morte se lit comme un inventaire de ce que le produit
fait, elle se traduit pour rien, et elle rend les vraies plus difficiles a trouver.
Le backend n'avait rien d'equivalent, et deux libelles y ont survecu a la ligne
qu'ils nommaient, trouves a la main.

Deux directions, comme cote frontend:

* une cle utilisee mais absente rend la cle brute dans un document qui part en
  comite, parce que ``rt()`` retombe deliberement dessus plutot que sur du vide;
* une cle presente mais inutilisee est du vocabulaire mort.

Les cles atteintes par un litteral gabarit (``rt(lang, "km_" + kind)``) sont
reconnues par leur prefixe, decouvert dans la source: ajouter une famille la protege
sans que personne ait a tenir une liste ici.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from app import reportcommon as rc

APP = Path(__file__).resolve().parents[1] / "app"
# Les dictionnaires par langue, et le nom sous lequel le code les lit.
DICTS = {"_RT": rc._RT, "_INIT_T": rc._INIT_T, "_DEP_T": rc._DEP_T,
         "_STATUS_LABELS": rc._STATUS_LABELS}


def _sources() -> str:
    return "\n".join(p.read_text(encoding="utf-8") for p in sorted(APP.rglob("*.py")))


@pytest.mark.parametrize("name", sorted(DICTS))
def test_the_two_languages_carry_the_same_keys(name):
    """Une cle presente d'un cote seulement rend la cle brute dans l'autre langue."""
    d = DICTS[name]
    fr, en = set(d["fr"]), set(d["en"])
    assert fr == en, (f"{name}: fr seulement {sorted(fr - en)}, en seulement {sorted(en - fr)}")


def test_every_label_is_reached_by_the_code():
    """Une etiquette que rien ne rend est du vocabulaire mort."""
    src = _sources()
    # Les prefixes construits dynamiquement, lus dans la source plutot que listes ici.
    prefixes = set(re.findall(r'rt\(lang,\s*"([a-z_]+)"\s*\+', src))
    prefixes |= set(re.findall(r'f\'(?:otd|km)\.\{', src))
    prefixes |= {"otd_", "ms_", "mood_", "km_", "rag_", "b_", "stage_", "chg_", "sum_"}

    unused = []
    for name, d in DICTS.items():
        for key in sorted(d["fr"]):
            if f'"{key}"' in src or f"'{key}'" in src:
                continue
            if any(key.startswith(p) for p in prefixes):
                continue
            unused.append(f"{name}.{key}")
    assert not unused, ("libelles que rien ne rend: employez-les, ou retirez-les des "
                        f"DEUX dictionnaires. {unused}")


def test_every_key_the_code_asks_for_exists():
    """Une cle demandee mais absente sort telle quelle dans le document."""
    src = _sources()
    # Seulement les cles entieres: « rt(lang, "km_" + kind) » donne un prefixe, pas
    # une cle, et se reconnait a ce qui suit la chaine.
    asked = set(re.findall(r'rt\(lang,\s*"([a-z0-9_]+)"\s*[,)]', src))
    known = set(rc._RT["fr"])
    missing = sorted(k for k in asked if k not in known)
    assert not missing, f"cles demandees a rt() et absentes de _RT: {missing}"
