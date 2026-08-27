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
           "c_jalon": "Jalon", "c_squad": "Squad · Tribu", "c_trim": "Trim.",
           "c_owner": "Owner", "c_status": "Statut",
           "t_tribe": "Tribu", "t_squad": "Squad", "t_text": "Externe",
           "gcount": "{n} jalon(s)"},
    "en": {"title": "Milestone dependencies", "suite": " (cont.)",
           "total": "{n} dependency(ies)", "none": "No dependency",
           "c_jalon": "Milestone", "c_squad": "Squad · Tribe", "c_trim": "Qtr",
           "c_owner": "Owner", "c_status": "Status",
           "t_tribe": "Tribe", "t_squad": "Squad", "t_text": "External",
           "gcount": "{n} milestone(s)"},
}


# Month labels for the roadmap, used by both the HTML timeline and the deck.
_MONTHS = {
    "fr": ["Janv", "Févr", "Mars", "Avr", "Mai", "Juin", "Juil", "Août", "Sept", "Oct", "Nov", "Déc"],
    "en": ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
}
