"""
Action Intelligence Service.

Orchestrates all Phase 7 engines to produce:
- Root cause groups
- Fix recommendations
- Blast radius analysis
- Effort estimates
- Developer action plan
- Repository health score
"""

from typing import List

from app.models.scored_finding import ScoredFinding
from app.models.root_cause import RootCauseGroup
from app.models.blast_radius import BlastRadius
from app.models.action_recommendation import ActionRecommendation
from app.models.developer_action_plan import ActionPlan
from app.models.repository_health import RepositoryHealth


def generate_action_intelligence(
    scored_findings: List[ScoredFinding],
    repository_path: str = "",
    repository_id: int = 0,
    analysis_id: int = 0,
) -> dict:
    """
    Run the full Phase 7 intelligence pipeline.

    Returns a dict with all Phase 7 outputs.
    """
    print("\n" + "=" * 60)
    print("  PHASE 7 -- ACTION INTELLIGENCE")
    print("=" * 60)

    # Step 1: Root Cause Analysis
    print("\n  [Phase 7] Step 1: Root cause analysis...")
    from app.engines.root_cause_engine import analyze_root_causes
    root_causes = analyze_root_causes(scored_findings)

    # Step 2: Fix Recommendations
    print("\n  [Phase 7] Step 2: Generating recommendations...")
    from app.engines.recommendation_engine import generate_recommendations
    recommendations = generate_recommendations(scored_findings)

    # Step 3: Blast Radius
    print("\n  [Phase 7] Step 3: Analyzing blast radius...")
    blast_radii = []
    if repository_path:
        from app.engines.blast_radius_engine import analyze_blast_radius
        blast_radii = analyze_blast_radius(scored_findings, repository_path)

    # Step 4: Effort & Impact
    print("\n  [Phase 7] Step 4: Estimating effort & impact...")
    from app.engines.effort_engine import estimate_effort_and_impact
    effort_data = estimate_effort_and_impact(
        scored_findings, blast_radii, recommendations
    )

    # Step 5: Action Plan
    print("\n  [Phase 7] Step 5: Building action plan...")
    from app.engines.action_plan_engine import generate_action_plan
    action_plan = generate_action_plan(
        scored_findings, effort_data, recommendations
    )
    action_plan.analysis_id = analysis_id

    # Step 6: Health Score
    print("\n  [Phase 7] Step 6: Calculating health score...")
    from app.engines.health_score_engine import calculate_health_score
    health = calculate_health_score(
        scored_findings, repository_id, analysis_id
    )

    print(f"\n  [Phase 7] Intelligence complete:")
    print(f"    Root cause groups: {len(root_causes)}")
    print(f"    Recommendations: {len(recommendations)}")
    print(f"    Blast radii: {len(blast_radii)}")
    print(f"    Action plan: {action_plan.now_count} NOW, "
          f"{action_plan.next_count} NEXT, {action_plan.later_count} LATER")
    print(f"    Health score: {health.overall_score}/100 ({health.health_level})")

    print("\n" + "=" * 60 + "\n")

    return {
        "root_causes": root_causes,
        "recommendations": recommendations,
        "blast_radii": blast_radii,
        "effort_data": effort_data,
        "action_plan": action_plan,
        "health": health,
    }
