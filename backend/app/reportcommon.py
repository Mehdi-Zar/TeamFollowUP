"""Pieces the report renderers share, whatever format they produce.

Split out of ``report`` so the PowerPoint renderers can live in their own module
without importing it back: these eleven declarations are the entire overlap
between the HTML side and the PPTX side. Anything that only one format needs
belongs in that format's module, not here.
"""
from __future__ import annotations

import html
import io
import os
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from . import pptxtpl
from . import status as st
from .generalconfig import get_general
from .models import Squad, Tribe, utcnow
from .serializers import annual_progress, budget_out, dependency_label


# All other report strings, by language.
_RT = {
    "fr": {
        "report": "Rapport hebdomadaire", "all_tribes": "Toutes les tribus",
        "year": "Année", "generated": "généré le", "window": "fenêtre {n} j",
        "generated_full": "Généré le {d}", "window_full": "Fenêtre {n} jours",
        "k_squads": "Squads", "k_progress": "Progression moy.", "k_blocked": "Jalons bloqués",
        "k_atrisk": "Jalons à risque", "k_obj_red": "Objectifs rouges", "k_stale": "Reporting périmé",
        "attention": "Points d'attention", "blocked_n": "bloqué(s)", "stale": "périmé",
        "h_squad": "Squad", "h_leader": "Responsable", "h_status": "Statut", "h_progress": "Progr.",
        "h_progress_long": "Progression", "h_delta": "Δ sem.", "h_blocked": "Bloqués",
        "h_atrisk": "À risque", "h_facts": "Faits de la semaine",
        "squad_scope": "Squad {name}", "more_squads": "… +{n} autres squads",
        "subject": "Rapport hebdomadaire - {scope} - semaine {w}", "synthesis": "Synthèse",
        "subject_personal": "Rapport - {scope} - {n} j",
        "detail_title": "Détail par squad", "h_objectives": "OTD",
        "h_roadmap": "Roadmap & jalons", "deadline": "échéance", "no_obj": "Aucun objectif",
        "no_jalon": "Aucun jalon", "dep": "Dép.", "roadmap_report": "Roadmap",
        "roadmap_subject": "Roadmap {year}",
        "stage_ea": "Accès anticipé", "stage_ga": "Disponibilité générale",
        "transverse_report": "Reporting transverse", "h_initiatives": "Initiatives",
        "no_initiative": "Aucune initiative", "h_jalons": "jalons", "h_objective": "Objectif",
        "h_jalon": "Jalon", "h_stage": "Phase", "h_otd": "OTD (engagements de livraison)",
        "no_otd": "Aucun OTD", "otd_commit": "engagé",
        "h_otd_section": "OTD", "h_freshness_ok": "Données à jour",
        # --- Frise annuelle (trimestres + engagements OTD + initiatives/jalons) ---
        "h_timeline": "Frise {year}", "tl_hint": "Les engagements OTD sur l'axe, puis les jalons de chaque initiative",
        "tl_empty": "Aucune initiative, aucun jalon",
        "tl_no_date": "Engagements sans date",
        "otd_on_track": "À l'heure", "otd_at_risk": "À risque", "otd_late": "En retard",
        "otd_delivered": "Livré",
        # --- Moral de l'equipe ---
        "h_mood": "Moral de l'équipe", "mood_good": "Ça va bien", "mood_mixed": "Moyen",
        "mood_bad": "Ça ne va pas", "mood_none": "Non renseigné", "mood_at": "soumis le {d}",
        "h_key_messages": "Messages clés", "no_key_message": "Aucun message clé",
        "km_success": "Succès", "km_alert": "Alerte", "km_risk": "Risque",
        "h_budget": "Budget", "no_budget": "Budget non renseigné",
        "b_total": "Total", "b_spent": "Consommé", "b_forecast": "Prévision",
        "b_on_track": "Sur les rails", "b_at_risk": "À risque", "b_over": "Dépassement",
        "leaves_upcoming": "Absences à venir (30 j)", "leaves_pending": "à valider", "days_short": "j",
        # --- "What's new since your last report" changelog ---
        "whatsnew": "Nouveautés depuis votre dernier rapport",
        "first_report": "Premier rapport - pas encore de comparaison.",
        "no_changes": "Aucun changement depuis le dernier rapport.",
        "subj_changes": "[{n} nouveauté(s)]", "subj_uptodate": "[à jour]",
        "chg_progress": "avancement {d} pts", "chg_status": "statut {frm} → {to}",
        "chg_ms_new": "nouveau jalon « {title} »", "chg_ms_status": "jalon « {title} » : {frm} → {to}",
        "chg_ms_removed": "jalon « {title} » retiré",
        "chg_obj_new": "nouvel OTD « {title} »", "chg_obj_status": "OTD « {title} » : {frm} → {to}",
        "chg_budget": "budget mis à jour", "chg_km": "{n} nouveau(x) message(s) clé(s)",
        "chg_stale": "reporting devenu périmé", "chg_unstale": "reporting de nouveau à jour",
        "chg_new_squad": "nouvelle squad « {name} »", "chg_squad_removed": "squad « {name} » retirée",
        "sum_moved": "{n} squad(s) ont bougé", "sum_delivered": "{n} jalon(s) livré(s)",
        "sum_blocked": "{n} nouveau(x) bloqueur(s)", "sum_stale": "{n} squad(s) périmée(s)",
        "ms_on_track": "En cours", "ms_at_risk": "À risque", "ms_blocked": "Bloqué", "ms_done": "Livré",
        "rag_green": "vert", "rag_amber": "orange", "rag_red": "rouge",
    },
    "en": {
        "report": "Weekly report", "all_tribes": "All tribes",
        "year": "Year", "generated": "generated on", "window": "window {n}d",
        "generated_full": "Generated on {d}", "window_full": "Window {n} days",
        "k_squads": "Squads", "k_progress": "Avg. progress", "k_blocked": "Blocked milestones",
        "k_atrisk": "At-risk milestones", "k_obj_red": "Red objectives", "k_stale": "Stale reporting",
        "attention": "Attention points", "blocked_n": "blocked", "stale": "stale",
        "h_squad": "Squad", "h_leader": "Leader", "h_status": "Status", "h_progress": "Progr.",
        "h_progress_long": "Progress", "h_delta": "Δ wk", "h_blocked": "Blocked",
        "h_atrisk": "At risk", "h_facts": "This week",
        "squad_scope": "Squad {name}", "more_squads": "… +{n} more squads",
        "subject": "Weekly report - {scope} - week {w}", "synthesis": "Summary",
        "subject_personal": "Report - {scope} - {n}d",
        "detail_title": "Detail by squad", "h_objectives": "OTD",
        "h_roadmap": "Roadmap & milestones", "deadline": "due", "no_obj": "No objective",
        "no_jalon": "No milestone", "dep": "Dep.", "roadmap_report": "Roadmap",
        "roadmap_subject": "Roadmap {year}",
        "stage_ea": "Early Access", "stage_ga": "General Availability",
        "transverse_report": "Transverse report", "h_initiatives": "Initiatives",
        "no_initiative": "No initiative", "h_jalons": "milestones", "h_objective": "Objective",
        "h_jalon": "Milestone", "h_stage": "Stage", "h_otd": "OTD (delivery commitments)",
        "no_otd": "No OTD", "otd_commit": "committed",
        "h_otd_section": "OTD", "h_freshness_ok": "Up to date",
        # --- Annual timeline (quarters + OTD commitments + initiatives/milestones) ---
        "h_timeline": "Timeline {year}", "tl_hint": "OTD commitments on the axis, then each initiative's milestones",
        "tl_empty": "No initiative, no milestone",
        "tl_no_date": "Commitments with no date",
        "otd_on_track": "On time", "otd_at_risk": "At risk", "otd_late": "Late",
        "otd_delivered": "Delivered",
        # --- Team mood ---
        "h_mood": "Team mood", "mood_good": "Good", "mood_mixed": "Mixed",
        "mood_bad": "Not good", "mood_none": "Not declared", "mood_at": "submitted on {d}",
        "h_key_messages": "Key messages", "no_key_message": "No key message",
        "km_success": "Success", "km_alert": "Alert", "km_risk": "Risk",
        "h_budget": "Budget", "no_budget": "Budget not set",
        "b_total": "Total", "b_spent": "Spent", "b_forecast": "Forecast",
        "b_on_track": "On track", "b_at_risk": "At risk", "b_over": "Over budget",
        "leaves_upcoming": "Upcoming absences (30 d)", "leaves_pending": "to approve", "days_short": "d",
        # --- "What's new since your last report" changelog ---
        "whatsnew": "What's new since your last report",
        "first_report": "First report - nothing to compare yet.",
        "no_changes": "No changes since the last report.",
        "subj_changes": "[{n} update(s)]", "subj_uptodate": "[up to date]",
        "chg_progress": "progress {d} pts", "chg_status": "status {frm} → {to}",
        "chg_ms_new": "new milestone “{title}”", "chg_ms_status": "milestone “{title}”: {frm} → {to}",
        "chg_ms_removed": "milestone “{title}” removed",
        "chg_obj_new": "new OTD “{title}”", "chg_obj_status": "OTD “{title}”: {frm} → {to}",
        "chg_budget": "budget updated", "chg_km": "{n} new key message(s)",
        "chg_stale": "reporting went stale", "chg_unstale": "reporting back up to date",
        "chg_new_squad": "new squad “{name}”", "chg_squad_removed": "squad “{name}” removed",
        "sum_moved": "{n} squad(s) moved", "sum_delivered": "{n} milestone(s) delivered",
        "sum_blocked": "{n} new blocker(s)", "sum_stale": "{n} squad(s) went stale",
        "ms_on_track": "On track", "ms_at_risk": "At risk", "ms_blocked": "Blocked", "ms_done": "Done",
        "rag_green": "green", "rag_amber": "amber", "rag_red": "red",
    },
}


def rt(lang: str, key: str, **kw) -> str:
    """Translate a report string by key, with optional str.format() interpolation.

    Falls back to the key itself if it is unknown (so a missing string is visible
    rather than crashing)."""
    s = _RT[_lang(lang)].get(key, key)
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
    "fr": {"title": "Initiatives", "h_init": "Initiative", "h_owner": "Owner",
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
           "c_jalon": "Jalon", "c_squad": "Squad (tribu)", "c_trim": "Trim.",
           "c_owner": "Owner", "c_status": "Statut",
           "t_tribe": "Tribu", "t_squad": "Squad", "t_text": "Externe",
           "gcount": "{n} jalon(s)", "cross_only": "hors tribu uniquement"},
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


def mood_label(mood: str | None, lang: str) -> str:
    """Libelle du moral declare, ou « non renseigne » quand il ne l'est pas."""
    return rt(lang, f"mood_{mood}") if mood in MOOD_EMOJI else rt(lang, "mood_none")


def timeline_rows(det: dict, lang: str) -> list[dict]:
    """Une ligne par initiative, portant les jalons qui la servent.

    Un jalon designe son initiative. Il l'a longtemps designee a travers son
    objectif annuel (jalon -> objectif -> initiative), un chemin dont aucun ecran
    ne posait le second maillon: chaque frise affichait alors des lignes
    d'initiative vides et une ligne anonyme portant tous les jalons. L'ancien
    chemin reste lu en second, pour des donnees qui n'auraient pas ete reprises.

    Les jalons qui ne servent rien, et ceux qui servent une initiative portee par
    une autre squad, se retrouvent dans une ligne « hors initiative » plutot que de
    disparaitre de la frise: un jalon absent d'un export se lit comme un jalon qui
    n'existe pas.
    """
    obj_to_init = {o["id"]: o.get("initiative_id") for o in det.get("objectives") or []}
    groups: dict[object, list[dict]] = {}
    for qd in det.get("quarters") or []:
        for it in qd.get("items") or []:
            key = (it.get("initiative_id")
                   or obj_to_init.get(it.get("objective_id")) or "none")
            groups.setdefault(key, []).append(dict(it, quarter=qd["q"]))

    rows: list[dict] = []
    known = set()
    for ini in det.get("initiatives") or []:
        known.add(ini["id"])
        rows.append({"key": ini["id"], "title": ini["title"], "owner": ini.get("owner"),
                     "deadline": ini.get("deadline"), "items": groups.get(ini["id"], [])})
    orphans = [it for key, items in groups.items() if key not in known for it in items]
    if orphans:
        # Sans titre, et non « Jalons hors initiative »: ces jalons ne forment pas
        # une categorie, ils sont ceux qui n'en ont pas. Nommer ce vide ajoute une
        # ligne a lire dans un document qui doit se lire de loin.
        rows.append({"key": "none", "title": None, "owner": None,
                     "deadline": None, "items": orphans})
    return rows


def pack_otds(otds: list[dict], *, chars_per_month: float, min_span: int = 2,
              max_span: int = 6, max_rows: int | None = None):
    """Range les engagements dates en bandes qui ne se chevauchent pas.

    La largeur d'un engagement suit la longueur de son titre, exprimee en mois:
    ``chars_per_month`` dit combien de caracteres tiennent dans une case, ce qui
    n'est pas la meme chose en HTML et sur une slide. Le bord gauche reste sur la
    date, qui est ce que la frise raconte; seule la largeur s'adapte.

    Rend (places, caches): places est une liste de (engagement, mois, largeur,
    bande), et caches compte ceux qui n'ont pas trouve de bande quand leur nombre
    est limite (la hauteur d'une slide, elle, ne s'etire pas).
    """
    placed: list[tuple[dict, int, int, int]] = []
    bands: list[list[tuple[int, int]]] = []
    hidden = 0
    for o in sorted((x for x in otds if x.get("month") is not None), key=lambda x: x["month"]):
        start = o["month"]
        need = -(-len(o.get("title") or "") // max(1, int(chars_per_month)))  # arrondi au mois superieur
        width = max(1, min(max(min_span, min(max_span, need)), 12 - start))
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
                placed.append((o, start, width, row))
                break
            row += 1
    return placed, hidden
