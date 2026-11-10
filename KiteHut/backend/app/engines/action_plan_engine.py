"""
Developer Action Plan Engine.

Organizes findings into NOW/NEXT/LATER action groups.
Considers priority, impact, confidence, blast radius, and effort.
"""

from typing import List

from app.models.scored_finding import ScoredFinding
from app.models.developer_action_plan import ActionPlan, ActionItem


def generate_action_plan(
    scored_findings: List[ScoredFinding],
    effort_data: list[dict],
    recommendations: list,
) -> ActionPlan:
    """
    Generate a developer action plan from scored findings.

    Groups findings into:
    - NOW (P0+P1): Fix immediately
    - NEXT (P2): Fix this sprint
    - LATER (P3+P4): Schedule for later
    """
    effort_map = {e["finding_id"]: e for e in effort_data}
    rec_map = {r.finding_id: r for r in recommendations}

    now_items = []
    next_items = []
    later_items = []

    for sf in scored_findings:
        effort_info = effort_map.get(sf.finding_id, {})
        rec = rec_map.get(sf.finding_id)

        item = ActionItem(
            finding_id=sf.finding_id,
            claim_type=sf.claim_type,
            statement=sf.original_claim,
            priority=sf.priority,
            final_score=sf.final_score,
            effort=effort_info.get("effort", "MEDIUM"),
            expected_impact=effort_info.get("expected_impact", "MEDIUM"),
            blast_radius=effort_info.get("blast_radius", "LOW"),
            recommendation_title=rec.title if rec else "",
        )

        if sf.priority in ("P0", "P1"):
            now_items.append(item)
        elif sf.priority == "P2":
            next_items.append(item)
        else:
            later_items.append(item)

    # Sort each group by final_score descending
    now_items.sort(key=lambda x: x.final_score, reverse=True)
    next_items.sort(key=lambda x: x.final_score, reverse=True)
    later_items.sort(key=lambda x: x.final_score, reverse=True)

    # Assign action order
    order = 1
    for item in now_items:
        item.action_order = order
        order += 1
    for item in next_items:
        item.action_order = order
        order += 1
    for item in later_items:
        item.action_order = order
        order += 1

    summary = _build_summary(now_items, next_items, later_items)

    plan = ActionPlan(
        analysis_id=0,  # Will be set by caller
        fix_now=now_items,
        fix_next=next_items,
        improve_later=later_items,
        total_actions=len(now_items) + len(next_items) + len(later_items),
        now_count=len(now_items),
        next_count=len(next_items),
        later_count=len(later_items),
        summary=summary,
    )

    print(f"  [ActionPlanEngine] Generated action plan: "
          f"{len(now_items)} NOW, {len(next_items)} NEXT, {len(later_items)} LATER")

    return plan


def _build_summary(now: list, next_items: list, later: list) -> str:
    """Build a human-readable summary of the action plan."""
    parts = []
    if now:
        parts.append(f"{len(now)} critical issues need immediate attention")
    if next_items:
        parts.append(f"{len(next_items)} issues should be addressed this sprint")
    if later:
        parts.append(f"{len(later)} issues can be scheduled for later")
    return ". ".join(parts) + "." if parts else "No actionable findings."
