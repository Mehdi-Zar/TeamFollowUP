from . import status as st
from .models import OrgNode, Squad
from .schemas import (
    KeyMessageOut,
    KpiOut,
    LeaderInfo,
    MemberOut,
    ObjectiveOut,
    OrgNodeTree,
    RoadmapItemOut,
    SquadBudgetOut,
    SquadCard,
    SquadDetail,
)


def leader_info(squad: Squad) -> LeaderInfo:
    if squad.leader is None:
        return LeaderInfo()
    return LeaderInfo(id=squad.leader.id, display_name=squad.leader.display_name, email=squad.leader.email)


def ref_quarter(year: int) -> int | None:
    cur_year, cur_q = st.current_year_quarter()
    return cur_q if year == cur_year else None


def annual_progress(squad: Squad, year: int) -> int:
    p = st.year_progress(squad, year)
    return round(sum(p.values()) / 4)


def objective_out(o, squad: Squad) -> ObjectiveOut:
    """ObjectiveOut whose rag_status is the auto-derived (not hand-entered) value."""
    out = ObjectiveOut.model_validate(o)
    out.rag_status = st.objective_status(o, squad)
    return out


def dependency_label(r) -> str | None:
    """Human label for a milestone dependency (squad/tribe name or the free text)."""
    kind = getattr(r, "dependency_kind", None)
    if kind == "squad":
        return r.dependency_squad.name if r.dependency_squad else None
    if kind == "tribe":
        return r.dependency_tribe.name if r.dependency_tribe else None
    return r.dependencies or None


def roadmap_item_out(r) -> RoadmapItemOut:
    out = RoadmapItemOut.model_validate(r)
    out.dependency_label = dependency_label(r)
    out.otd_label = r.otd.title if getattr(r, "otd", None) else None
    return out


# Spending is "at risk" once the reference figure reaches this share of the envelope.
BUDGET_AT_RISK_RATIO = 0.9


def budget_out(squad: Squad, year: int) -> SquadBudgetOut:
    """Budget readout for the year. Status is driven by the projected landing
    (forecast, falling back to spent) versus the total envelope - so 'at risk'
    surfaces before any euro is overspent."""
    row = next((b for b in squad.budgets if b.year == year), None)

    def num(v):
        return float(v) if v is not None else None

    total = num(row.total) if row else None
    spent = num(row.spent) if row else None
    forecast = num(row.forecast) if row else None
    reference = forecast if forecast is not None else spent   # what the squad will land at

    status = "on_track"
    overrun = 0.0
    overrun_pct = 0
    if total is not None and total > 0 and reference is not None:
        ratio = reference / total
        if reference > total:
            status = "over"
            overrun = round(reference - total, 2)
            overrun_pct = round(overrun / total * 100)
        elif ratio >= BUDGET_AT_RISK_RATIO:
            status = "at_risk"

    pct = lambda v: round(v / total * 100) if (total and total > 0 and v is not None) else None
    return SquadBudgetOut(
        total=total, spent=spent, forecast=forecast,
        comment=row.comment if row else None,
        status=status, spent_pct=pct(spent), forecast_pct=pct(forecast),
        overrun=overrun, overrun_pct=overrun_pct,
        updated_at=row.updated_at if row else None,
    )


def squad_detail(squad: Squad, year: int, threshold: int, privileged: bool = False) -> SquadDetail:
    progress = st.year_progress(squad, year)
    comments = st.quarter_comments(squad, year)
    return SquadDetail(
        id=squad.id,
        tribe_id=squad.tribe_id,
        name=squad.name,
        description=squad.description,
        leader_user_id=squad.leader_user_id,
        display_order=squad.display_order,
        kpis_enabled=squad.kpis_enabled,
        budget_enabled=squad.budget_enabled,
        squad_type=squad.squad_type,
        products=squad.products or [],
        hardware=squad.hardware or [],
        leader=leader_info(squad),
        year=year,
        annual_progress=annual_progress(squad, year),
        freshness=st.freshness(squad, threshold),
        counts=st.counts(squad, year),
        quarter_progress={str(q): {"progress_pct": progress[q], "comment": comments[q]} for q in (1, 2, 3, 4)},
        objectives=[objective_out(o, squad) for o in sorted(squad.objectives, key=lambda x: x.id) if o.year == year],
        roadmap_items=[roadmap_item_out(r) for r in
                       sorted(squad.roadmap_items, key=lambda x: (x.quarter, x.display_order, x.id)) if r.year == year],
        kpis=[KpiOut.model_validate(k) for k in sorted(squad.kpis, key=lambda x: x.id)],
        members=[MemberOut.model_validate(m) for m in sorted(squad.members, key=lambda x: (x.display_order, x.id))],
        key_messages=[KeyMessageOut.model_validate(m) for m in
                      sorted(squad.key_messages, key=lambda x: (x.display_order, x.id)) if m.year == year],
        # Budget figures are restricted to the squad leader, its tribe leader and admins.
        budget=budget_out(squad, year) if (privileged and squad.budget_enabled) else None,
    )


def squad_card(squad: Squad, year: int, threshold: int) -> SquadCard:
    progress = st.year_progress(squad, year)
    blocked = st.blocked_count(squad, year, None)
    at_risk = st.at_risk_count(squad, year, None)
    risk = 3 if blocked > 0 else 2 if at_risk > 0 else 1
    return SquadCard(
        squad_id=squad.id,
        name=squad.name,
        tribe_id=squad.tribe_id,
        tribe_name=squad.tribe.name if squad.tribe else None,
        leader=leader_info(squad),
        annual_progress=annual_progress(squad, year),
        risk_rank=risk,
        focus_quarter=ref_quarter(year),
        quarter_progress={str(q): progress[q] for q in (1, 2, 3, 4)},
        quarter_breakdowns={str(q): st.quarter_breakdown(squad, year, q) for q in (1, 2, 3, 4)},
        blocked_count=blocked,
        at_risk_count=at_risk,
        counts=st.counts(squad, year),
        members_count=len(squad.members),
        freshness=st.freshness(squad, threshold),
    )


def build_org_tree(nodes: list[OrgNode], squad_status: dict[int, str]) -> list[OrgNodeTree]:
    by_parent: dict[int | None, list[OrgNode]] = {}
    for n in nodes:
        by_parent.setdefault(n.parent_id, []).append(n)
    for children in by_parent.values():
        children.sort(key=lambda n: (n.display_order, n.id))

    def build(node: OrgNode) -> OrgNodeTree:
        return OrgNodeTree(
            id=node.id,
            parent_id=node.parent_id,
            title=node.title,
            person_name=node.person_name,
            squad_id=node.squad_id,
            squad_status=squad_status.get(node.squad_id) if node.squad_id else None,
            display_order=node.display_order,
            children=[build(c) for c in by_parent.get(node.id, [])],
        )

    return [build(n) for n in by_parent.get(None, [])]
