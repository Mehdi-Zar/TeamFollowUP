"""Les couleurs des courbes KPI, verifiees par le calcul et non a l'oeil.

Deux des six tenaient du meme bleu marine: sur le graphe d'une plateforme, deux
courbes etaient litteralement de la meme couleur et la legende restait le seul
moyen de les separer. Un ecart de couleur se mesure, donc il se teste, et c'est
la seule facon d'empecher qu'une retouche de palette le ramene.

La mesure est l'ecart euclidien dans l'espace OKLab, multiplie par 100: c'est
l'unite des outils de verification de palette, ou 15 est le plancher entre deux
couleurs voisines et 8 la cible une fois simulee une deficience de vision des
couleurs. La simulation utilise les matrices de Machado (2009), les memes.
"""
from __future__ import annotations

import itertools
import math

from app.routers.steerco import SERIES_COLORS

# Le fond sur lequel ces courbes sont tracees, dans les deux rendus.
SURFACE = "#FFFFFF"
# Ce qui, sur cette page, veut dire quelque chose: la sante d'un SLA et les
# incidents. Une courbe ne doit pas avoir l'air de le dire aussi.
STATUS_COLORS = ["#027A48", "#B54708", "#B42318", "#D24545"]

MACHADO = {
    "protan": ((0.152286, 1.052583, -0.204868),
               (0.114503, 0.786281, 0.099216),
               (-0.003882, -0.048116, 1.051998)),
    "deutan": ((0.367322, 0.860646, -0.227968),
               (0.280085, 0.672501, 0.047413),
               (-0.011820, 0.042940, 0.968881)),
}


def _linear(hexcolor: str) -> tuple[float, float, float]:
    """sRGB -> lineaire, le prealable de toute mesure de couleur."""
    raw = [int(hexcolor.lstrip("#")[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    return tuple(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in raw)


def _oklab(rgb: tuple[float, float, float]) -> tuple[float, float, float]:
    r, g, b = rgb
    l = (0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b) ** (1 / 3)
    m = (0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b) ** (1 / 3)
    s = (0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b) ** (1 / 3)
    return (0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s,
            1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s,
            0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s)


def _simulate(rgb, kind: str):
    m = MACHADO[kind]
    return tuple(min(1.0, max(0.0, sum(m[i][j] * rgb[j] for j in range(3)))) for i in range(3))


def delta_e(a: str, b: str, kind: str | None = None) -> float:
    """L'ecart entre deux couleurs, vu normalement ou avec une deficience."""
    ra, rb = _linear(a), _linear(b)
    if kind:
        ra, rb = _simulate(ra, kind), _simulate(rb, kind)
    pa, pb = _oklab(ra), _oklab(rb)
    return 100 * math.dist(pa, pb)


def _contrast(a: str, b: str) -> float:
    lum = lambda h: sum(k * c for k, c in zip((0.2126, 0.7152, 0.0722), _linear(h)))
    hi, lo = sorted((lum(a), lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def test_two_neighbouring_series_are_never_close():
    """Deux couleurs qui se suivent portent souvent deux courbes voisines.

    C'est la paire la plus exposee, donc celle qui tient le plancher le plus
    haut: 15 a vision normale, et 8 une fois simulee une protanopie ou une
    deuteranopie, ou le rouge et le vert se rejoignent.
    """
    worst_normal = min((delta_e(a, b), a, b)
                       for a, b in zip(SERIES_COLORS, SERIES_COLORS[1:]))
    assert worst_normal[0] >= 15, worst_normal
    worst_cvd = min((delta_e(a, b, kind), kind, a, b)
                    for kind in MACHADO
                    for a, b in zip(SERIES_COLORS, SERIES_COLORS[1:]))
    assert worst_cvd[0] >= 8, worst_cvd


def test_no_two_series_share_a_colour():
    """Et aucune paire, meme eloignee dans la liste, ne se confond.

    Six couleurs sur un fond clair ne peuvent pas toutes etre a 15 les unes des
    autres, c'est une contrainte du gamut et non un reglage. Mais elles peuvent
    toutes se distinguer: le plancher est ici 12, la ou les deux bleus marine
    d'avant etaient a 5,5, c'est a dire a rien.
    """
    worst = min((delta_e(a, b), a, b) for a, b in itertools.combinations(SERIES_COLORS, 2))
    assert worst[0] >= 12, worst


def test_every_series_reads_on_white_and_means_nothing():
    """Deux choses a la fois: se voir, et ne rien dire.

    Se voir, c'est 3 pour 1 de contraste sur le fond: en dessous, un trait de
    deux points s'efface au videoprojecteur, ce qui est arrive a un gris-bleu
    pale et a un ambre clair. Ne rien dire, c'est rester loin du vert, de
    l'ambre et du rouge qui, sur cette meme page, annoncent la sante d'un SLA et
    les incidents.
    """
    faint = [(c, round(_contrast(c, SURFACE), 2)) for c in SERIES_COLORS
             if _contrast(c, SURFACE) < 3.0]
    assert not faint, faint
    looks_like_status = [(c, s, round(delta_e(c, s), 1)) for c in SERIES_COLORS
                         for s in STATUS_COLORS if delta_e(c, s) < 10]
    assert not looks_like_status, looks_like_status
