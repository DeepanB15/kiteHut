"""
Severity Engine.

Determines how severe a finding is based on its type, context, and category.
This is the first layer of the Phase 4 scoring pipeline.

Severity levels:
  CRITICAL (80-100): Exploitable security flaws, data loss risks
  HIGH     (60-79):  Significant security or reliability issues
  MEDIUM   (40-59):  Quality/maintainability concerns
  LOW      (20-39):  Minor issues, style, best practices
  INFO     (0-19):   Observations, no action required
"""

from app.models.claim import Claim
from app.models.scored_finding import SeverityResult


# ============================================================
# Base severity scores by claim type
# ============================================================

CLAIM_TYPE_SEVERITY = {
    # Security risks — highest severity
    "hardcoded_secret": 95,
    "missing_authentication": 90,
    "missing_authorization": 85,
    "weak_input_validation": 80,
    "debug_mode_enabled": 70,
    "insecure_configuration": 75,

    # Architecture issues
    "tight_coupling": 50,
    "layer_violation": 55,
    "missing_separation": 45,
    "god_class": 40,
    "circular_dependency": 55,

    # Quality issues
    "code_duplication": 35,
    "large_function": 40,
    "large_class": 35,
    "poor_error_handling": 60,
    "naming_issue": 20,

    # Testing issues
    "missing_tests": 50,
    "low_test_coverage": 45,
    "missing_integration_tests": 40,
    "missing_test_framework": 55,
}


def calculate_severity(claim: Claim) -> SeverityResult:
    """
    Calculate severity for a verified finding.

    Uses claim type as the primary factor, with adjustments
    based on the claim category and statement keywords.
    """
    base_score = CLAIM_TYPE_SEVERITY.get(claim.claim_type, 30)

    # Keyword-based adjustments
    statement_lower = claim.statement.lower()

    # Boost for critical security keywords
    critical_keywords = ["remote", "rce", "injection", "authentication bypass", "data leak"]
    if any(kw in statement_lower for kw in critical_keywords):
        base_score = min(100, base_score + 15)

    # Boost for production/deployment context
    prod_keywords = ["production", "deploy", "public", "internet", "exposed"]
    if any(kw in statement_lower for kw in prod_keywords):
        base_score = min(100, base_score + 10)

    # Reduce for development-only context
    dev_keywords = ["development", "dev only", "local", "test", "staging"]
    if any(kw in statement_lower for kw in dev_keywords):
        base_score = max(0, base_score - 15)

    # Determine level
    if base_score >= 80:
        level = "CRITICAL"
    elif base_score >= 60:
        level = "HIGH"
    elif base_score >= 40:
        level = "MEDIUM"
    elif base_score >= 20:
        level = "LOW"
    else:
        level = "INFO"

    reasoning = _build_severity_reasoning(claim, base_score, level)

    return SeverityResult(
        level=level,
        score=round(base_score, 1),
        reasoning=reasoning,
    )


def _build_severity_reasoning(
    claim: Claim, score: float, level: str
) -> str:
    """Build human-readable reasoning for the severity score."""
    parts = []
    parts.append(f"Claim type '{claim.claim_type}' has base severity {CLAIM_TYPE_SEVERITY.get(claim.claim_type, 30)}")

    if claim.category == "security_risk":
        parts.append("Security findings receive elevated severity")
    elif claim.category == "quality_issue":
        parts.append("Quality findings receive moderate severity")
    elif claim.category == "testing_issue":
        parts.append("Testing gaps affect long-term reliability")
    elif claim.category == "architecture_issue":
        parts.append("Architecture issues affect maintainability")

    parts.append(f"Final severity: {level} ({score}/100)")
    return ". ".join(parts)
