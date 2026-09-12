"""Personnalisation de l'apparence: couleurs, logos, typographie, densite.

Le theme de l'application est deja pilote par des variables CSS sur ``:root``.
Rendre ces variables administrables ne demande donc pas de reconstruire quoi que
ce soit: le serveur publie un theme, la page l'applique, et un changement de
couleur se voit au rechargement suivant.

**Ce qui sort d'ici part dans une feuille de style et dans des balises d'image.**
Une valeur libre y serait une injection: ``--navy: red; } body { display:none } /*``
suffirait a casser l'application pour tout le monde, et une URL arbitraire ferait
charger une image par un tiers a chaque affichage. Toute valeur est donc validee
par forme, pas seulement par longueur:

* une couleur doit etre ``#rgb`` ou ``#rrggbb``, rien d'autre;
* une image doit etre une ``data:`` URI d'image, donc embarquee, jamais une URL
  distante: le rendu ne doit dependre d'aucun serveur tiers, et une capture de
  l'ecran de connexion ne doit pas fuiter vers un domaine qu'on ne controle pas;
* une police est choisie dans une liste fermee, parce que le nom part tel quel
  dans ``font-family``;
* les nombres sont bornes, une valeur hors bornes etant ramenee dans les bornes
  plutot que refusee: un rayon de 400 pixels est une erreur de saisie, pas une
  raison d'echouer.

Ce qui n'est pas ici et n'a pas a y etre: le nom et le sous-titre de
l'application (``generalconfig``, ils existaient avant), l'ecran de connexion
(``authconfig``, voir docs/22) et le gabarit PPTX (``pptxtpl``). L'ecran de
personnalisation les rassemble a l'affichage, chacun reste stocke chez lui.
"""
from __future__ import annotations

import json
import re

from sqlalchemy.orm import Session

from .models import AppSetting

BRANDING_KEY = "branding"

HEX = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")
# Images embarquees uniquement. Le poids est plafonne parce que ce blob est lu a
# chaque chargement de page, par tout le monde, y compris avant authentification.
MAX_IMAGE_CHARS = 400_000
MAX_TEXT = 300

# Les piles de polices proposees. Fermee: le nom part tel quel dans font-family.
FONTS = {
    "system": 'Calibri, Carlito, "Segoe UI", system-ui, sans-serif',
    "grotesque": '"Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
    "serif": 'Georgia, "Times New Roman", serif',
    "mono": '"Cascadia Mono", Consolas, "SF Mono", Menlo, monospace',
}

# Variable CSS -> cle de configuration. L'ecran d'administration se construit a
# partir de cette table, donc ajouter une couleur ici suffit a la rendre reglable.
COLORS = {
    "navy": "--navy",
    "navy_deep": "--navy-deep",
    "accent": "--accent",
    "ice_blue": "--ice-blue",
    "ice_soft": "--ice-soft",
    "green": "--green",
    "orange": "--orange",
    "red": "--red",
    "text": "--text",
    "grey": "--grey",
    "line": "--line",
    "bg": "--bg",
}


def defaults() -> dict:
    """Le theme livre. Les couleurs reprennent celles de ``theme.css``: une valeur
    vide cote client voudrait dire "pas de couleur", pas "la couleur par defaut"."""
    return {
        "navy": "#1E2761",
        "navy_deep": "#141B47",
        "accent": "#175CD3",
        "ice_blue": "#CADCFC",
        "ice_soft": "#E8F0FE",
        "green": "#027A48",
        "orange": "#B54708",
        "red": "#B42318",
        "text": "#1E293B",
        "grey": "#64748B",
        "line": "#E2E8F0",
        "bg": "#F5F7FA",
        "font": "system",
        "font_scale": 100,      # pourcentage, 85 a 125
        "radius": 14,           # pixels, 0 a 24
        "density": "comfortable",   # comfortable | compact
        "shadows": True,
        "logo": "",            # en-tete de l'application
        "favicon": "",
        "login_background": "",     # image de fond de l'ecran de connexion
        "document_logo": "",        # exports HTML et PPTX
        "email_footer": "",
    }


KEYS = set(defaults().keys())


def _color(value, fallback: str) -> str:
    v = str(value or "").strip()
    return v if HEX.match(v) else fallback


def _image(value) -> str:
    """Une image embarquee, ou rien. Une URL distante est refusee, pas tronquee:
    la garder a moitie donnerait une balise cassee plutot qu'une absence."""
    v = str(value or "").strip()
    if not v.startswith("data:image/"):
        return ""
    return v[:MAX_IMAGE_CHARS]


def _int(value, fallback: int, lo: int, hi: int) -> int:
    try:
        return max(lo, min(hi, int(value)))
    except (TypeError, ValueError):
        return fallback


def sanitize(raw: dict | None) -> dict:
    """Un theme sur lequel la page peut ecrire sans reflechir.

    Chaque champ absent ou refuse retombe sur le defaut, donc le resultat est
    toujours complet: la page n'a jamais a arbitrer entre "non defini" et "vide".
    """
    base = defaults()
    raw = raw if isinstance(raw, dict) else {}
    out = dict(base)
    for key in COLORS:
        out[key] = _color(raw.get(key), base[key])
    out["font"] = raw.get("font") if raw.get("font") in FONTS else base["font"]
    out["font_scale"] = _int(raw.get("font_scale"), base["font_scale"], 85, 125)
    out["radius"] = _int(raw.get("radius"), base["radius"], 0, 24)
    out["density"] = raw.get("density") if raw.get("density") in ("comfortable", "compact") else base["density"]
    out["shadows"] = bool(raw.get("shadows", base["shadows"]))
    for key in ("logo", "favicon", "login_background", "document_logo"):
        out[key] = _image(raw.get(key))
    out["email_footer"] = str(raw.get("email_footer") or "").strip()[:MAX_TEXT]
    return out


def get_branding(db: Session) -> dict:
    cfg = defaults()
    row = db.get(AppSetting, BRANDING_KEY)
    if row:
        try:
            cfg.update({k: v for k, v in json.loads(row.value).items() if k in KEYS})
        except (json.JSONDecodeError, TypeError):
            pass
    return sanitize(cfg)


def set_branding(db: Session, patch: dict | None) -> dict:
    """Applique une modification partielle. ``{"reset": true}`` revient au theme
    livre, ce qui est la seule facon sure de sortir d'une combinaison illisible."""
    if (patch or {}).get("reset"):
        cfg = defaults()
    else:
        cfg = get_branding(db)
        for k, v in (patch or {}).items():
            if k in KEYS:
                cfg[k] = v
        cfg = sanitize(cfg)
    row = db.get(AppSetting, BRANDING_KEY)
    payload = json.dumps(cfg)
    if row is None:
        db.add(AppSetting(key=BRANDING_KEY, value=payload))
    else:
        row.value = payload
    return cfg


def css_variables(cfg: dict) -> dict[str, str]:
    """Le theme sous la forme que la page applique: des variables CSS.

    Construit ici plutot que cote client pour que le nom des variables reste
    decide au meme endroit que leur validation.
    """
    out = {css: cfg[key] for key, css in COLORS.items() if cfg.get(key)}
    out["--radius"] = f"{cfg['radius']}px"
    out["--font-family"] = FONTS.get(cfg["font"], FONTS["system"])
    out["--font-scale"] = f"{cfg['font_scale'] / 100:.2f}"
    out["--density"] = "6px" if cfg["density"] == "compact" else "12px"
    if not cfg["shadows"]:
        out["--shadow"] = "none"
    return out
