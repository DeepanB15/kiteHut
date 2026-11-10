"""
Effort & Impact Prediction Engine.

Estimates the effort required to fix a finding and the expected impact.
"""

from typing import List

from app.models.scored_finding import ScoredFinding
from app.models.blast_radius import BlastRadius
from app.models.action_recommendation import ActionRecommendation


# Effort estimation by claim type
EFFORT_MAP = {
    "hardcoded_secret": "LOW",
    "debug_mode_enabled": "LOW",
    "naming_issue": "LOW",
    "code_duplication": "LOW",
    "missing_test_framework": "LOW",
    "large_function": "LOW",
    "missing_tests": "MEDIUM",
    "low_test_coverage": "MEDIUM",
    "poor_error_handling": "MEDIUM",
    "weak_input_validation": "MEDIUM",
    "missing_integration_tests": "MEDIUM",
    "large_class": "MEDIUM",
    "tight_coupling": "HIGH",
    "layer_violation": "HIGH",
    "missing_separation": "HIGH",
    "missing_authentication": "HIGH",
    "missing_authorization": "HIGH",
    "insecure_configuration": "MEDIUM",
    "circular_dependency": "VERY_HIGH",
}

# Expected impact by claim type
IMPACT_MAP = {
    "hardcoded_secret": "CRITICAL",
    "missing_authentication": "CRITICAL",
    "missing_authorization": "HIGH",
    "weak_input_validation": "HIGH",
    "debug_mode_enabled": "HIGH",
    "insecure_configuration": "HIGH",
    "poor_error_handling": "MEDIUM",
    "missing_tests": "MEDIUM",
    "low_test_coverage": "MEDIUM",
    "missing_test_framework": "MEDIUM",
    "missing_integration_tests": "MEDIUM",
    "tight_coupling": "MEDIUM",
    "layer_violation": "MEDIUM",
    "missing_separation": "MEDIUM",
    "large_function": "LOW",
    "large_class": "LOW",
    "code_duplication": "LOW",
    "circular_dependency": "MEDIUM",
    "naming_issue": "LOW",
}


def estimate_effort_and_impact(
    scored_findings: List[ScoredFinding],
    blast_radii: List[BlastRadius],
    recommendations: List[ActionRecommendation],
) -> List[dict]:
    """
    Estimate effort and expected impact for each finding.

    Returns a list of dicts with finding_id, effort, expected_impact, blast_radius.
    """
    radius_map = {br.finding_id: br for br in blast_radii}
    rec_map = {r.finding_id: r for r in recommendations}

    results = []

    for sf in scored_findings:
        base_effort = EFFORT_MAP.get(sf.claim_type, "MEDIUM")
        base_impact = IMPACT_MAP.get(sf.claim_type, "MEDIUM")

        # Adjust effort based on blast radius
        radius = radius_map.get(sf.finding_id)
        if radius:
            if radius.radius_level in ("HIGH", "CRITICAL"):
                # Large blast radius increases effort
                effort_order = ["LOW", "MEDIUM", "HIGH", "VERY_HIGH"]
                idx = effort_order.index(base_effort) if base_effort in effort_order else 1
                base_effort = effort_order[min(idx + 1, len(effort_order) - 1)]

        # Adjust impact based on severity
        if sf.severity.level == "CRITICAL":
            base_impact = "CRITICAL"
        elif sf.severity.level == "HIGH" and base_impact in ("MEDIUM", "LOW"):
            base_impact = "HIGH"

        results.append({
            "finding_id": sf.finding_id,
            "effort": base_effort,
            "expected_impact": base_impact,
            "blast_radius": radius.radius_level if radius else "LOW",
        })

    print(f"  [EffortEngine] Estimated effort for {len(results)} findings.")

    return results
