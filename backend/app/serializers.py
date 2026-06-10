from . import status as st
from .models import OrgNode, Squad
from .schemas import (
    KpiOut,
    LeaderInfo,
    MemberOut,
    ObjectiveOut,
    OrgNodeTree,
    RoadmapItemOut,
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


def squad_detail(squad: Squad, year: int, threshold: int) -> SquadDetail:
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
        leader=leader_info(squad),
        year=year,
        annual_progress=annual_progress(squad, year),
        freshness=st.freshness(squad, threshold),
        counts=st.counts(squad, year),
        quarter_progress={str(q): {"progress_pct": progress[q], "comment": comments[q]} for q in (1, 2, 3, 4)},
        objectives=[ObjectiveOut.model_validate(o) for o in sorted(squad.objectives, key=lambda x: x.id) if o.year == year],
        roadmap_items=[RoadmapItemOut.model_validate(r) for r in
                       sorted(squad.roadmap_items, key=lambda x: (x.quarter, x.display_order, x.id)) if r.year == year],
        kpis=[KpiOut.model_validate(k) for k in sorted(squad.kpis, key=lambda x: x.id)],
        members=[MemberOut.model_validate(m) for m in sorted(squad.members, key=lambda x: (x.display_order, x.id))],
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
