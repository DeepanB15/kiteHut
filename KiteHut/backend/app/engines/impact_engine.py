"""
Impact Engine.

Analyzes the impact of a finding across three dimensions:
  - User Impact: How does this affect end users?
  - System Impact: How does this affect system reliability/security?
  - Business Impact: How does this affect business objectives?

Each dimension is scored 0-100, then combined into an overall impact score.
"""

from app.models.claim import Claim
from app.models.scored_finding import ImpactResult


# ============================================================
# Impact scoring rules by claim type
# ============================================================

# (user_impact, system_impact, business_impact) base scores
IMPACT_MAP = {
    # Security
    "hardcoded_secret":          (70, 95, 85),
    "missing_authentication":    (80, 90, 90),
    "missing_authorization":     (60, 85, 80),
    "weak_input_validation":     (50, 80, 60),
    "debug_mode_enabled":        (30, 60, 40),
    "insecure_configuration":    (40, 75, 50),

    # Architecture
    "tight_coupling":            (20, 50, 40),
    "layer_violation":           (15, 45, 35),
    "missing_separation":        (15, 40, 30),
    "god_class":                 (25, 55, 45),
    "circular_dependency":       (20, 60, 40),

    # Quality
    "code_duplication":          (10, 35, 30),
    "large_function":            (15, 40, 25),
    "large_class":               (10, 35, 25),
    "poor_error_handling":       (50, 65, 55),
    "naming_issue":              (5, 15, 10),

    # Testing
    "missing_tests":             (20, 45, 50),
    "low_test_coverage":         (15, 40, 45),
    "missing_integration_tests": (25, 50, 40),
    "missing_test_framework":    (20, 40, 45),
}


def calculate_impact(claim: Claim) -> ImpactResult:
    """
    Calculate impact scores for a finding.

    Returns user, system, and business impact scores, plus
    a weighted overall impact.
    """
    base = IMPACT_MAP.get(claim.claim_type, (20, 30, 25))
    user_impact, system_impact, business_impact = base

    statement_lower = claim.statement.lower()

    # Boosts for high-impact keywords
    if any(kw in statement_lower for kw in ["production", "public", "customer", "user data"]):
        user_impact = min(100, user_impact + 15)
        business_impact = min(100, business_impact + 15)

    if any(kw in statement_lower for kw in ["authentication", "authorization", "security"]):
        system_impact = min(100, system_impact + 10)

    # Reduce for internal/tooling context
    if any(kw in statement_lower for kw in ["internal", "tool", "script", "utility"]):
        user_impact = max(0, user_impact - 15)
        business_impact = max(0, business_impact - 15)

    # Weighted overall: user 30%, system 45%, business 25%
    overall = (
        user_impact * 0.30
        + system_impact * 0.45
        + business_impact * 0.25
    )

    reasoning = _build_impact_reasoning(
        claim, user_impact, system_impact, business_impact, overall
    )

    return ImpactResult(
        user_impact=round(user_impact, 1),
        system_impact=round(system_impact, 1),
        business_impact=round(business_impact, 1),
        overall_impact=round(overall, 1),
        reasoning=reasoning,
    )


def _build_impact_reasoning(
    claim: Claim,
    user: float, system: float, business: float, overall: float,
) -> str:
    """Build human-readable reasoning for impact scores."""
    parts = []
    parts.append(f"Impact analysis for '{claim.claim_type}'")
    parts.append(f"User impact: {user}, System impact: {system}, Business impact: {business}")
    parts.append(f"Overall impact: {overall:.0f}/100 (weighted: 30% user, 45% system, 25% business)")
    return ". ".join(parts)
