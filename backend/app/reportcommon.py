"""Pieces the report renderers share, whatever format they produce.

Split out of ``report`` so the PowerPoint renderers can live in their own module
without importing it back: these eleven declarations are the entire overlap
between the HTML side and the PPTX side. Anything that only one format needs
belongs in that format's module, not here.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

from .models import Squad, Tribe


# All other report strings, by language.
_RT = {
    "fr": {
        "report": "Rapport hebdomadaire", "dashboard_doc": "Tableau de bord", "all_tribes": "Toutes les tribes",
        "year": "Année", "generated": "généré le", "window": "fenêtre {n} j",
        "generated_full": "Généré le {d}", "window_full": "Fenêtre {n} jours",
        "k_squads": "Squads", "k_progress": "Progression moy.", "k_blocked": "Jalons bloqués",
        "k_atrisk": "Jalons à risque", "k_otd_late": "OTD en retard", "k_stale": "Reporting périmé",
        "attention": "Points d'attention", "blocked_n": "bloqué(s)", "stale": "périmé",
        "h_squad": "Squad", "h_leader": "Squad leader", "h_co_leaders": "Co-leaders", "h_contributors": "Contributeurs", "h_status": "Statut", "h_progress": "Progr.",
        "h_progress_long": "Progression", "h_delta": "Δ sem.", "h_blocked": "Bloqués",
        "h_atrisk": "À risque", "h_facts": "Faits de la semaine",
        "squad_scope": "Squad {name}", "more_squads": "… +{n} autres squads",
        "subject": "Rapport hebdomadaire | {scope} | semaine {w}", "synthesis": "Synthèse",
        "subject_personal": "Rapport | {scope} | semaine {w}",
        "detail_title": "Détail par squad", "h_objectives": "OTD",
        "h_roadmap": "Roadmap & jalons", "deadline": "échéance",
        "no_jalon": "Aucun jalon", "dep": "Dép.", "roadmap_report": "Roadmap",
        "roadmap_subject": "Roadmap {year}",
        "stage_ea": "Accès anticipé", "stage_ga": "Disponibilité générale",
        "transverse_report": "Reporting transverse", "h_initiatives": "Initiatives",
        "no_initiative": "Aucune initiative", "h_jalons": "jalons",
        "h_jalon": "Jalon", "h_stage": "Phase", "h_otd": "OTD (engagements de livraison)",
        "no_otd": "Aucun OTD", "otd_commit": "engagé",
        "h_otd_section": "OTD", "h_freshness_ok": "Données à jour",
        # --- Versions: un document rejoué à une date passée ---
        "as_of_full": "version du {d}", "as_of_missing": "{n} squads sans saisie à cette date", "as_of_missing_one": "{n} squad sans saisie à cette date",
        "as_of_live": "Version courante",
        # --- Frise annuelle (trimestres + engagements OTD + leurs jalons) ---
        "h_timeline": "Frise {year}", "tl_hint": "Les engagements OTD sur l'axe, et sous chaque mois les jalons attendus",
        "tl_empty": "Aucun engagement, aucun jalon",
        "h_commitments": "Engagements et jalons",
        "otd_scope_management": "Engagement management",
        "otd_scope_squad": "Engagement de la squad",
        "tl_no_date": "Engagements sans date",
        "q_nothing": "rien de prévu",
        "h_tribe_otds": "Engagements de la tribe portés par aucune squad",
        "tl_no_date_short": "sans date",
        "more_items": "+{n} autres, dans la version HTML",
        "tl_dropped": "Non affichés faute de place ({n})",
        "otd_on_track": "Dans les temps", "otd_at_risk": "À risque", "otd_late": "En retard",
        "otd_delivered": "Livré",
        # --- Moral de l'equipe ---
        "h_mood": "Moral de l'équipe", "mood_l1": "Moral", "mood_l2": "équipe",
        "mood_good": "Ça va bien", "mood_mixed": "Moyen",
        "mood_bad": "Ça ne va pas", "mood_none": "Non renseigné", "mood_at": "déclaré le {d}",
        "h_key_messages": "Messages clés", "no_key_message": "Aucun message clé",
        "km_success": "Succès", "km_alert": "Alerte", "km_risk": "Risque",
        "h_budget": "Budget", "no_budget": "Budget non renseigné",
        "b_total": "Total", "b_spent": "Consommé", "b_forecast": "Prévision",
        "b_on_track": "Sur les rails", "b_at_risk": "À risque", "b_over": "Dépassement",
        "leaves_upcoming": "Absences à venir (30 j)", "leaves_pending": "à valider", "days_short": "j",
        # --- "What's new since your last report" changelog ---
        "whatsnew": "Nouveautés depuis votre dernier rapport",
        "first_report": "Premier rapport : pas encore de comparaison.",
        "no_changes": "Aucun changement depuis le dernier rapport.",
        "subj_changes": "[{n} nouveautés]", "subj_changes_one": "[{n} nouveauté]", "subj_uptodate": "[aucun changement]",
        "chg_progress": "avancement {d} pts", "chg_status": "statut {frm} → {to}",
        "chg_ms_new": "nouveau jalon « {title} »", "chg_ms_status": "jalon « {title} » : {frm} → {to}",
        "chg_ms_removed": "jalon « {title} » retiré",
        "chg_obj_new": "nouvel OTD « {title} »", "chg_obj_status": "OTD « {title} » : {frm} → {to}",
        "chg_budget": "budget mis à jour", "chg_km": "{n} nouveaux messages clés", "chg_km_one": "{n} nouveau message clé",
        "chg_stale": "reporting devenu périmé", "chg_unstale": "reporting de nouveau à jour",
        "chg_new_squad": "nouvelle squad « {name} »", "chg_squad_removed": "squad « {name} » retirée",
        "sum_moved": "{n} squads ont bougé", "sum_moved_one": "{n} squad a bougé", "sum_delivered": "{n} jalons livrés", "sum_delivered_one": "{n} jalon livré",
        "sum_blocked": "{n} nouveaux bloqueurs", "sum_blocked_one": "{n} nouveau bloqueur", "sum_stale": "{n} squads périmées", "sum_stale_one": "{n} squad périmée",
        "ms_on_track": "En cours", "ms_at_risk": "À risque", "ms_blocked": "Bloqué", "ms_done": "Livré",
        "rag_green": "vert", "rag_amber": "orange", "rag_red": "rouge",
    },
    "en": {
        "report": "Weekly report", "dashboard_doc": "Dashboard", "all_tribes": "All tribes",
        "year": "Year", "generated": "generated on", "window": "window {n}d",
        "generated_full": "Generated on {d}", "window_full": "Window {n} days",
        "k_squads": "Squads", "k_progress": "Avg. progress", "k_blocked": "Blocked milestones",
        "k_atrisk": "At-risk milestones", "k_otd_late": "Late OTDs", "k_stale": "Stale reporting",
        "attention": "Attention points", "blocked_n": "blocked", "stale": "stale",
        "h_squad": "Squad", "h_leader": "Squad leader", "h_co_leaders": "Co-leaders", "h_contributors": "Contributors", "h_status": "Status", "h_progress": "Progr.",
        "h_progress_long": "Progress", "h_delta": "Δ wk", "h_blocked": "Blocked",
        "h_atrisk": "At risk", "h_facts": "This week",
        "squad_scope": "Squad {name}", "more_squads": "… +{n} more squads",
        "subject": "Weekly report | {scope} | week {w}", "synthesis": "Summary",
        "subject_personal": "Report | {scope} | week {w}",
        "detail_title": "Detail by squad", "h_objectives": "OTD",
        "h_roadmap": "Roadmap & milestones", "deadline": "due",
        "no_jalon": "No milestone", "dep": "Dep.", "roadmap_report": "Roadmap",
        "roadmap_subject": "Roadmap {year}",
        "stage_ea": "Early Access", "stage_ga": "General Availability",
        "transverse_report": "Transverse report", "h_initiatives": "Initiatives",
        "no_initiative": "No initiative", "h_jalons": "milestones",
        "h_jalon": "Milestone", "h_stage": "Stage", "h_otd": "OTD (delivery commitments)",
        "no_otd": "No OTD", "otd_commit": "committed",
        "h_otd_section": "OTD", "h_freshness_ok": "Up to date",
        # --- Versions: a document replayed at a past date ---
        "as_of_full": "version of {d}", "as_of_missing": "{n} squads with no submission at that date", "as_of_missing_one": "{n} squad with no submission at that date",
        "as_of_live": "Current version",
        # --- Annual timeline (quarters + OTD commitments + their milestones) ---
        "h_timeline": "Timeline {year}", "tl_hint": "OTD commitments on the axis, and under each month the milestones it expects",
        "tl_empty": "No commitment, no milestone",
        "h_commitments": "Commitments and milestones",
        "otd_scope_management": "Management commitment",
        "otd_scope_squad": "Squad commitment",
        "tl_no_date": "Commitments with no date",
        "q_nothing": "nothing planned",
        "h_tribe_otds": "Tribe commitments no squad carries",
        "tl_no_date_short": "no date",
        "more_items": "+{n} more, in the HTML version",
        "tl_dropped": "Not shown for lack of room ({n})",
        "otd_on_track": "On time", "otd_at_risk": "At risk", "otd_late": "Late",
        "otd_delivered": "Delivered",
        # --- Team mood ---
        "h_mood": "Team mood", "mood_l1": "Team", "mood_l2": "Mood",
        "mood_good": "Good", "mood_mixed": "Mixed",
        "mood_bad": "Not good", "mood_none": "Not declared", "mood_at": "declared on {d}",
        "h_key_messages": "Key messages", "no_key_message": "No key message",
        "km_success": "Success", "km_alert": "Alert", "km_risk": "Risk",
        "h_budget": "Budget", "no_budget": "Budget not set",
        "b_total": "Total", "b_spent": "Spent", "b_forecast": "Forecast",
        "b_on_track": "On track", "b_at_risk": "At risk", "b_over": "Over budget",
        "leaves_upcoming": "Upcoming absences (30 d)", "leaves_pending": "to approve", "days_short": "d",
        # --- "What's new since your last report" changelog ---
        "whatsnew": "What's new since your last report",
        "first_report": "First report: nothing to compare yet.",
        "no_changes": "No changes since the last report.",
        "subj_changes": "[{n} updates]", "subj_changes_one": "[{n} update]", "subj_uptodate": "[no change]",
        "chg_progress": "progress {d} pts", "chg_status": "status {frm} → {to}",
        "chg_ms_new": "new milestone “{title}”", "chg_ms_status": "milestone “{title}”: {frm} → {to}",
        "chg_ms_removed": "milestone “{title}” removed",
        "chg_obj_new": "new OTD “{title}”", "chg_obj_status": "OTD “{title}”: {frm} → {to}",
        "chg_budget": "budget updated", "chg_km": "{n} new key messages", "chg_km_one": "{n} new key message",
        "chg_stale": "reporting went stale", "chg_unstale": "reporting back up to date",
        "chg_new_squad": "new squad “{name}”", "chg_squad_removed": "squad “{name}” removed",
        "sum_moved": "{n} squads moved", "sum_moved_one": "{n} squad moved", "sum_delivered": "{n} milestones delivered", "sum_delivered_one": "{n} milestone delivered",
        "sum_blocked": "{n} new blockers", "sum_blocked_one": "{n} new blocker", "sum_stale": "{n} squads went stale", "sum_stale_one": "{n} squad went stale",
        "ms_on_track": "On track", "ms_at_risk": "At risk", "ms_blocked": "Blocked", "ms_done": "Done",
        "rag_green": "green", "rag_amber": "amber", "rag_red": "red",
    },
}


def _people_line(r: dict, lang: str, e=lambda x: x) -> str:
    """", Co-leaders : A, B, Contributeurs : C" when the squad has any."""
    out = ""
    if r.get("co_leaders"):
        out += f', {e(rt(lang, "h_co_leaders"))}{_sep(lang)}{e(", ".join(r["co_leaders"]))}'
    if r.get("contributors"):
        out += f', {e(rt(lang, "h_contributors"))}{_sep(lang)}{e(", ".join(r["contributors"]))}'
    return out


# Documents are read in Paris: a timestamp stored in UTC is shown in local time.
DISPLAY_TZ = "Europe/Paris"
_MON_EN = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _paris(d):
    """UTC to Paris time. The tz database when there is one; otherwise the EU rule
    itself (summer time from the last Sunday of March to the last Sunday of
    October, at 01:00 UTC), so a server without tzdata still shows local time."""
    try:
        from zoneinfo import ZoneInfo
        return d.astimezone(ZoneInfo(DISPLAY_TZ))
    except Exception:
        def last_sunday(year: int, month: int):
            nxt = datetime(year + (month == 12), month % 12 + 1, 1, tzinfo=timezone.utc)
            last = nxt - timedelta(days=1)
            return (last - timedelta(days=(last.weekday() + 1) % 7)).replace(hour=1)
        u = d.astimezone(timezone.utc)
        summer = last_sunday(u.year, 3) <= u < last_sunday(u.year, 10)
        return u.astimezone(timezone(timedelta(hours=2 if summer else 1)))


def fmt_date(value, lang: str) -> str:
    """A date as a reader of this language writes it: 23/09/2026, or 23 Sep 2026.
    Accepts an ISO string (date or date-time) or a date; anything else unchanged."""
    from datetime import date
    if value in (None, ""):
        return "-"
    d = value
    if isinstance(value, str):
        try:
            d = datetime.fromisoformat(value.replace("Z", "+00:00")) if "T" in value or " " in value \
                else date.fromisoformat(value[:10])
        except ValueError:
            return value
    if isinstance(d, datetime):
        d = d.date()
    return f"{d.day:02d}/{d.month:02d}/{d.year}" if _lang(lang) == "fr" else f"{d.day} {_MON_EN[d.month - 1]} {d.year}"


def fmt_datetime(value, lang: str) -> str:
    """A timestamp in Paris time: 23/09/2026 14:05 (FR) or 23 Sep 2026 14:05."""
    if value in (None, ""):
        return "-"
    d = value
    if isinstance(value, str):
        try:
            d = datetime.fromisoformat(value.replace("Z", "+00:00").replace(" ", "T"))
        except ValueError:
            return value
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    d = _paris(d)
    return f"{fmt_date(d.date().isoformat(), lang)} {d.hour:02d}:{d.minute:02d}"


def fmt_money(v, lang: str) -> str:
    """An amount: 1 200 000 € in French (narrow no-break spaces), €1,200,000 in English."""
    if v is None:
        return "-"
    if _lang(lang) == "fr":
        return f"{v:,.0f}".replace(",", "\u202f") + "\u00a0€"
    return f"€{v:,.0f}"


def _sep(lang: str) -> str:
    """A label's colon: spaced in French, tight in English."""
    return " : " if _lang(lang) == "fr" else ": "


def rt(lang: str, key: str, **kw) -> str:
    """Translate a report string by key, with optional str.format() interpolation.

    Falls back to the key itself if it is unknown (so a missing string is visible
    rather than crashing)."""
    table = _RT[_lang(lang)]
    # Singular form when there is one ("key_one"): 1 in both languages, and 0 in
    # French ("0 nouveauté"), as the interface does. No more "(s)".
    n = kw.get("n")
    if isinstance(n, int) and (n == 1 or (n == 0 and _lang(lang) == "fr")) and f"{key}_one" in table:
        key = f"{key}_one"
    s = table.get(key, key)
    return s.format(**kw) if kw else s


def _lang(lang: str | None) -> str:
    """Normalize a language hint to a supported code ('en' or, by default, 'fr')."""
    return "en" if lang == "en" else "fr"


STAGE_COLOR = {"EA": "#FFC000", "GA": "#00B050"}


_STATUS_RAG = {"blocked": "red", "at_risk": "amber", "on_track": "green",
               "done": "green", "red": "red", "amber": "amber", "green": "green"}


_STATUS_LABELS = {
    "fr": {"blocked": "Bloqué", "at_risk": "À risque", "on_track": "En cours",
           "done": "Terminé", "red": "Rouge", "amber": "Orange", "green": "Vert"},
    "en": {"blocked": "Blocked", "at_risk": "At risk", "on_track": "On track",
           "done": "Done", "red": "Red", "amber": "Amber", "green": "Green"},
}


def _status_rag(status: str | None) -> str:
    """Map a milestone/objective status code to its RAG colour ('grey' if unknown)."""
    return _STATUS_RAG.get(status or "", "grey")


def _status_label(status: str | None, lang: str = "fr") -> str:
    """Localized human label for a status code ('-' when absent/unknown)."""
    return _STATUS_LABELS[_lang(lang)].get(status or "", status or "-")


def group_by_theme(items: list[dict]) -> list[tuple[str, list[dict]]]:
    """Group roadmap items by their theme, preserving first-seen order.

    A blank/missing theme yields an empty key (rendered without a header)."""
    groups: list[tuple[str, list[dict]]] = []
    index: dict[str, int] = {}
    for it in items:
        key = (it.get("theme") or "").strip()
        if key not in index:
            index[key] = len(groups)
            groups.append((key, []))
        groups[index[key]][1].append(it)
    return groups


# ----- Initiatives list (flat: initiative / owner / squad / deadline) -------------

_INIT_T = {
    "fr": {"title": "Initiatives", "h_init": "Initiative", "h_owner": "Porteur",
           "h_squad": "Squad", "h_deadline": "Échéance", "none": "Aucune initiative", "year": "Année"},
    "en": {"title": "Initiatives", "h_init": "Initiative", "h_owner": "Owner",
           "h_squad": "Squad", "h_deadline": "Deadline", "none": "No initiative", "year": "Year"},
}


# =============================================================================
# Milestone-dependency deck: every jalon that depends on another tribe / squad /
# external actor, grouped by the entity it waits on. Table format, paginated so
# no dependency is ever silently dropped. mode="cross_tribe" (default) keeps only
# dependencies that cross a tribe boundary; mode="all" keeps every dependency.
# =============================================================================

_DEP_T = {
    "fr": {"title": "Dépendances des jalons", "suite": " (suite)",
           "total": "{n} dépendance(s)", "none": "Aucune dépendance",
           "c_jalon": "Jalon", "c_squad": "Squad (tribe)", "c_trim": "Trim.",
           "c_owner": "Porteur", "c_status": "Statut",
           "t_tribe": "Tribe", "t_squad": "Squad", "t_text": "Externe",
           "gcount": "{n} jalon(s)", "cross_only": "hors tribe uniquement"},
    "en": {"title": "Milestone dependencies", "suite": " (cont.)",
           "total": "{n} dependency(ies)", "none": "No dependency",
           "c_jalon": "Milestone", "c_squad": "Squad (tribe)", "c_trim": "Qtr",
           "c_owner": "Owner", "c_status": "Status",
           "t_tribe": "Tribe", "t_squad": "Squad", "t_text": "External",
           "gcount": "{n} milestone(s)", "cross_only": "cross-tribe only"},
}


# Month labels for the roadmap, used by both the HTML timeline and the deck.
_MONTHS = {
    "fr": ["Janv", "Févr", "Mars", "Avr", "Mai", "Juin", "Juil", "Août", "Sept", "Oct", "Nov", "Déc"],
    "en": ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
}


# =============================================================================
# La frise annuelle, partagee par les trois exports (HTML, JPG, PPTX).
#
# Les initiatives, les engagements OTD et les jalons repondaient a la meme
# question, "ou en est l'annee", dans trois blocs separes. Ici ils sont ramenes
# sur un seul axe: le temps est la seule chose qu'ils ont en commun, et c'est ce
# qui permet de les lire d'un regard.
#
# Le regroupement ne cree aucune donnee: le chainage existe deja en base, une
# initiative porte des objectifs et un objectif porte des jalons. Cette fonction
# se contente de le suivre.
# =============================================================================

# Les trois niveaux du moral, et le visage qui les porte. Fermes: un quatrieme
# niveau arriverait par l'API et aucun export ne saurait l'afficher.
MOOD_EMOJI = {"good": "\U0001F600", "mixed": "\U0001F610", "bad": "\U0001F641"}
MOOD_COLOR = {"good": "green", "mixed": "amber", "bad": "red"}

# La couleur qui distingue les deux portees d'engagement, partout: bandeau de la
# frise, libelle de ligne, legende, HTML comme PPTX. Le bleu de marque pour ce qui
# vient du management, un cyan profond pour ce que la squad prend elle-meme. Deux
# teintes soutenues et non une pale: sur un videoprojecteur, une nuance claire
# disparait, et c'est justement la distinction qui est demandee.
OTD_SCOPE_COLOR = {"management": "#1E2761", "squad": "#0E7490"}

# Le moral se dessine en nuage plutot qu'en emoji. Un emoji depend de la police
# installee: il sort en carre sur un poste sans jeu couleur, et il change de style
# d'un support a l'autre. Un nuage dessine sort pareil partout, et il reste sobre.
# Trois teintes: la couleur porte le niveau, la bouche le redit pour qui imprime
# en noir et blanc.
# Le nuage est **plein** et non pastel: pose en haut d'une slide a cote d'un
# bandeau navy, une teinte claire cernee d'un filet fin disparaissait. La couleur
# porte le niveau, le visage le redit pour qui imprime en noir et blanc.
MOOD_CLOUD = {
    "good": {"ink": "#027A48", "fill": "#7EE2B8"},
    "mixed": {"ink": "#B54708", "fill": "#FBD96B"},
    "bad": {"ink": "#B42318", "fill": "#F9A8A0"},
}


# Le contour du nuage et son visage, decrits **une seule fois**, dans un repere de
# 64 x 46. Le HTML les rend en arcs et en courbes SVG; la slide, qui ne connait que
# des segments, les rend en polygones echantillonnes sur ces memes arcs. Tant que
# la slide utilisait la forme « nuage » de PowerPoint, l'icone du document n'etait
# pas celle de l'application: meme couleur, autre dessin, donc autre logo.
MOOD_CLOUD_BOX = (64.0, 46.0)
MOOD_CLOUD_D = "M18 40 A11 11 0 0 1 18 18 A13 13 0 0 1 43 14 A11 11 0 0 1 47 40 Z"
_MOOD_CLOUD_ARCS = (((18.0, 40.0), (18.0, 18.0), 11.0),
                    ((18.0, 18.0), (43.0, 14.0), 13.0),
                    ((43.0, 14.0), (47.0, 40.0), 11.0))
MOOD_CLOUD_EYES = (((26.0, 23.0), 2.8), ((39.0, 23.0), 2.8))
MOOD_CLOUD_STROKE = 3.0
# Les bouches, dans le meme repere: sourire, trait, moue. Une courbe quadratique
# (depart, controle, arrivee) ou, pour « moyen », un simple segment.
MOOD_CLOUD_MOUTH = {
    "good": ((24.0, 27.0), (32.0, 35.0), (40.0, 27.0)),
    "mixed": ((25.0, 29.0), None, (39.0, 29.0)),
    "bad": ((24.0, 33.0), (32.0, 25.0), (40.0, 33.0)),
}


def _arc_points(p0, p1, radius, steps):
    """Les points d'un arc SVG (large-arc=0, sweep=1), depart exclu.

    Deux centres satisfont un couple de points et un rayon; le drapeau de sens
    en designe un seul, celui dont l'arc parcouru dans le sens des angles
    croissants fait moins d'un demi-tour.
    """
    (x0, y0), (x1, y1) = p0, p1
    dx, dy = x1 - x0, y1 - y0
    span = math.hypot(dx, dy)
    radius = max(radius, span / 2)
    off = math.sqrt(max(0.0, radius * radius - (span / 2) ** 2))
    mx, my = (x0 + x1) / 2, (y0 + y1) / 2
    ux, uy = -dy / span, dx / span
    chosen = None
    for sign in (1.0, -1.0):
        cx, cy = mx + sign * off * ux, my + sign * off * uy
        a0 = math.atan2(y0 - cy, x0 - cx)
        sweep = (math.atan2(y1 - cy, x1 - cx) - a0) % (2 * math.pi)
        if sweep <= math.pi + 1e-9:
            chosen = (cx, cy, a0, sweep)
            break
    cx, cy, a0, sweep = chosen
    return [(cx + radius * math.cos(a0 + sweep * i / steps),
             cy + radius * math.sin(a0 + sweep * i / steps))
            for i in range(1, steps + 1)]


def mood_cloud_outline(steps: int = 12) -> list[tuple[float, float]]:
    """Le contour du nuage en polygone ferme, dans le repere de 64 x 46."""
    points = [_MOOD_CLOUD_ARCS[0][0]]
    for p0, p1, radius in _MOOD_CLOUD_ARCS:
        points.extend(_arc_points(p0, p1, radius, steps))
    return points


def mood_cloud_mouth_points(mood: str, steps: int = 10) -> list[tuple[float, float]]:
    """La bouche en ligne brisee, dans le meme repere. Vide si le moral est inconnu."""
    curve = MOOD_CLOUD_MOUTH.get(mood or "")
    if curve is None:
        return []
    (x0, y0), control, (x2, y2) = curve
    if control is None:
        return [(x0, y0), (x2, y2)]
    cx, cy = control
    out = []
    for i in range(steps + 1):
        t = i / steps
        u = 1 - t
        out.append((u * u * x0 + 2 * u * t * cx + t * t * x2,
                    u * u * y0 + 2 * u * t * cy + t * t * y2))
    return out


def mood_cloud_svg(mood: str | None, size: int = 34) -> str:
    """Le nuage du moral, en SVG autonome (aucune police, aucune image externe).

    Rendu vide pour un moral non declare: un nuage gris se lirait comme un moral
    moyen, alors que « non renseigne » n'est pas un niveau.
    """
    palette = MOOD_CLOUD.get(mood or "")
    if palette is None:
        return ""
    ink, fill = palette["ink"], palette["fill"]
    # La bouche dit le niveau sans la couleur: sourire, trait, moue.
    mouth = {
        "good": "M24 27 Q32 35 40 27",
        "mixed": "M25 29 L39 29",
        "bad": "M24 33 Q32 25 40 33",
    }[mood]
    h = int(size * 0.72)
    return (
        f'<svg class="mood-cloud" width="{size}" height="{h}" viewBox="0 0 64 46" '
        f'role="img" aria-hidden="true" focusable="false">'
        f'<path d="{MOOD_CLOUD_D}" '
        f'fill="{fill}" stroke="{ink}" stroke-width="{MOOD_CLOUD_STROKE:g}" '
        f'stroke-linejoin="round"/>'
        f'<circle cx="26" cy="23" r="2.8" fill="{ink}"/>'
        f'<circle cx="39" cy="23" r="2.8" fill="{ink}"/>'
        f'<path d="{mouth}" fill="none" stroke="{ink}" stroke-width="3" '
        f'stroke-linecap="round"/>'
        f'</svg>'
    )


# L'etoile d'un engagement, dessinee et non prise dans une police. Meme raison
# que le nuage du moral: un caractere « etoile » sort en carre sur un poste qui
# n'a pas le jeu, et le deck, lui, dessine deja une forme.
_STAR_PATH = ("M12 1.8 L14.9 8.4 L22 9.2 L16.6 13.9 L18.2 21 "
              "L12 17.3 L5.8 21 L7.4 13.9 L2 9.2 L9.1 8.4 Z")


def version_suffix(data: dict, lang: str) -> str:
    """Ce qui suit « genere le ... » quand le document rejoue une date passee.

    Un document date qui ne se dit pas date est le pire des deux mondes: il a
    l'air du rapport d'aujourd'hui et il en donne les chiffres d'hier. La mention
    voyage donc avec l'heure de generation, dans les quatre rendus, et elle compte
    les squads qui n'avaient rien soumis a cette date plutot que de les taire.
    """
    if not data.get("as_of"):
        return ""
    out = ", " + rt(lang, "as_of_full", d=fmt_date(data["as_of"], lang))
    missing = data.get("as_of_missing") or []
    if missing:
        out += ", " + rt(lang, "as_of_missing", n=len(missing))
    return out


def otd_star_svg(scope: str, size: int = 13) -> str:
    """L'etoile qui pose un engagement sur son mois, a la couleur de sa portee."""
    color = OTD_SCOPE_COLOR.get(scope, OTD_SCOPE_COLOR["management"])
    return (f'<svg class="xtl-star" width="{size}" height="{size}" viewBox="0 0 24 24" '
            f'role="img" aria-hidden="true" focusable="false">'
            f'<path d="{_STAR_PATH}" fill="{color}"/></svg>')


def mood_label(mood: str | None, lang: str) -> str:
    """Libelle du moral declare, ou « non renseigne » quand il ne l'est pas."""
    return rt(lang, f"mood_{mood}") if mood in MOOD_EMOJI else rt(lang, "mood_none")


def milestone_theme(item: dict, initiatives: dict) -> str | None:
    """Le theme d'un jalon: l'initiative qu'il sert, ou le theme saisi a la main.

    Les deux disent la meme chose, « de quoi parle ce jalon », et un squad leader
    utilise l'un ou l'autre selon que le sujet a ete porte au rang d'initiative ou
    non. Un jalon sans l'un ni l'autre n'a pas de theme: il n'appartient pas a une
    categorie « sans theme », il n'appartient a rien.
    """
    title = initiatives.get(item.get("initiative_id"))
    if title:
        return title
    return (item.get("theme") or "").strip() or None


def quarter_slots(groups: list[dict]) -> list[tuple[float, float]]:
    """La place de chaque boite, en colonnes de mois, dans son trimestre.

    Une boite **ne sort jamais du trimestre de sa date**: elle peut commencer un
    mois plus tot que celle-ci pour tenir dans les trois colonnes, mais elle n'en
    deborde pas. Une boite de decembre qui s'etalait sur l'annee suivante n'avait
    nulle part ou aller, et une boite a cheval sur deux trimestres se lisait sous
    le mauvais.

    Les boites d'un meme trimestre s'en partagent les trois colonnes, dans l'ordre
    de leurs dates. Rend, pour chacune, (debut, largeur) exprimes en colonnes.
    """
    slots: dict[int, list[int]] = {}
    for i, g in enumerate(groups):
        slots.setdefault(g["month"] // 3, []).append(i)
    out: list[tuple[float, float]] = [(0.0, 3.0)] * len(groups)
    for quarter, indexes in slots.items():
        width = 3.0 / len(indexes)
        for rank, i in enumerate(indexes):
            out[i] = (quarter * 3 + rank * width, width)
    return out


def wrap_lines(text: str, cpl: int) -> int:
    """Sur combien de lignes ce texte tombe, coupe aux espaces.

    Compter les caracteres et diviser par la largeur sous-estime des qu'un mot ne
    tient pas sur la fin d'une ligne: « Premiere region secondaire ouverte » sur
    dix-sept caracteres fait trois lignes, pas deux, et le titre suivant se
    retrouvait dessous. PowerPoint coupe aux espaces, et ne coupe un mot que s'il
    est a lui seul plus long que la ligne.
    """
    cpl = max(1, int(cpl))
    lines, used = 1, 0
    for word in (text or "").split():
        need = len(word) if used == 0 else len(word) + 1
        if used + need <= cpl:
            used += need
            continue
        lines += 1
        used = len(word)
        while used > cpl:
            used -= cpl
            lines += 1
    return lines


def timeline_groups(det: dict) -> list[dict]:
    """Une boite de jalons par engagement, et une par theme pour le reste.

    Une boite porte un titre et **une seule date**, ce qui est la condition pour
    qu'un trait suffise a dire quand ses jalons sont attendus. Le titre est
    l'engagement que ces jalons tiennent; a defaut d'engagement, le theme, c'est a
    dire l'initiative qu'ils servent ou le theme que leur squad leader a saisi.

    Les jalons sans engagement se groupent par theme **et par trimestre**: un
    theme dont les jalons tombent en mars et en octobre ferait deux promesses dans
    une boite qui n'en montre qu'une.

    Un jalon qui tient deux engagements figure dans les deux boites: ce sont deux
    promesses distinctes, et taire l'une reviendrait a dire qu'elle n'existe pas.

    Rend les boites dans l'ordre des dates, ce qui est ce qui permet ensuite de
    les poser sans que leurs traits se croisent.
    """
    otds = {o["id"]: o for o in det.get("otds") or []}
    initiatives = {i["id"]: i.get("title") for i in det.get("initiatives") or []}
    held: dict[object, list] = {}
    orphans: dict[tuple, list] = {}
    for qd in det.get("quarters") or []:
        for it in qd.get("items") or []:
            item = dict(it, quarter=qd["q"])
            keys = [k for k in (it.get("otd_id"), it.get("squad_otd_id"))
                    if k is not None and k in otds]
            if keys:
                for key in keys:
                    held.setdefault(key, []).append(item)
            else:
                orphans.setdefault((milestone_theme(it, initiatives) or "", qd["q"]),
                                   []).append(item)

    groups: list[dict] = []
    for key, items in held.items():
        otd = otds[key]
        month = otd.get("month")
        if month is None:
            # Un engagement sans date se pose au milieu du trimestre de son premier
            # jalon: sans cela sa boite n'aurait aucun trait, donc aucune date.
            month = (min(it["quarter"] for it in items) - 1) * 3 + 1
        # Le titre de la boite est l'engagement que ses jalons tiennent. Il est
        # certes deja ecrit au-dessus, sur son etoile, mais la boite n'est pas
        # posee sous cette etoile: elle est rangee dans l'ordre des dates, et son
        # trait seul dirait « cette date-la » sans dire « cette promesse-la ».
        groups.append({"title": otd["title"], "scope": otd.get("scope") or "management",
                       "status": otd.get("status"),
                       "month": month, "dated": otd.get("month") is not None,
                       "items": items})
    for (theme, quarter), items in orphans.items():
        groups.append({"title": theme or None, "scope": None,
                       "month": (quarter - 1) * 3 + 1, "dated": False, "items": items})
    groups.sort(key=lambda g: (g["month"], g["title"] or ""))
    return groups


def pack_bands(items: list[dict], span_of, *, max_rows: int | None = None,
               columns: int = 12):
    """Range des reperes dates en bandes qui ne se recouvrent pas.

    Un repere est pose sur son mois et son libelle s'ecrit a cote; la place que
    prend ce libelle, ``span_of`` la rend en nombre de colonnes, parce qu'elle ne
    se mesure pas pareil sur une slide et dans une page web. Quand deux libelles
    se recouvrent, le second descend d'une bande.

    En fin d'annee il n'y a plus rien a droite du repere: le bloc recule alors
    pour tenir dans l'annee, et son libelle s'ecrit a gauche du repere. Le repere,
    lui, ne bouge jamais de sa date: c'est ``item["month"]`` qui le pose, et
    jamais le ``debut`` rendu ici.

    Rend (places, caches): places est une liste de (item, debut, largeur, bande),
    et caches compte ceux qui n'ont pas trouve de bande quand leur nombre est
    limite (la hauteur d'une slide, elle, ne s'etire pas).
    """
    placed: list[tuple[dict, int, int, int]] = []
    bands: list[list[tuple[int, int]]] = []
    hidden = 0
    for it in sorted((x for x in items if x.get("month") is not None),
                     key=lambda x: (x["month"], x.get("title") or "")):
        month = it["month"]
        width = max(1, min(columns, int(span_of(it))))
        # En fin d'annee le bloc recule juste assez pour que son libelle tienne a
        # GAUCHE du repere, et pas plus: cale sur la fin de l'annee, il reservait
        # des colonnes a droite du repere, la ou le libelle ne s'ecrit pas.
        start = month if month + width <= columns else max(0, month + 1 - width)
        end = start + width
        row = 0
        while True:
            if max_rows is not None and row >= max_rows:
                hidden += 1
                break
            if row == len(bands):
                bands.append([])
            if all(end <= a or start >= b for a, b in bands[row]):
                bands[row].append((start, end))
                placed.append((it, start, width, row))
                break
            row += 1
    return placed, hidden
