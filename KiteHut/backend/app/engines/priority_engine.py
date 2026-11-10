"""
Priority Engine.

Combines all scoring dimensions into a final priority score and rank.

Final Priority Score (0-100) =
    Severity        x 35%
  + Impact          x 30%
  + Confidence      x 20%
  + Exploitability  x 15%

Priority levels:
  P0 / CRITICAL: score >= 80
  P1 / HIGH:     score >= 60
  P2 / MEDIUM:   score >= 40
  P3 / LOW:      score >= 20
  P4 / INFO:     score < 20
"""

from typing import List

from app.models.claim import Claim
from app.models.scored_finding import (
    ScoredFinding,
    SeverityResult,
    ImpactResult,
    ExploitabilityResult,
    SEVERITY_CRITICAL,
    SEVERITY_HIGH,
    SEVERITY_MEDIUM,
    SEVERITY_LOW,
    SEVERITY_INFO,
    PRIORITY_P0,
    PRIORITY_P1,
    PRIORITY_P2,
    PRIORITY_P3,
    PRIORITY_P4,
)


# ============================================================
# Scoring weights
# ============================================================

SEVERITY_WEIGHT = 0.35
IMPACT_WEIGHT = 0.30
CONFIDENCE_WEIGHT = 0.20
EXPLOITABILITY_WEIGHT = 0.15


def calculate_final_score(
    severity: SeverityResult,
    impact: ImpactResult,
    confidence: float,
    exploitability: ExploitabilityResult,
) -> float:
    """
    Calculate the final priority score.

    Formula:
        score = severity * 35% + impact * 30%
              + confidence * 20% + exploitability * 15%

    Returns a score between 0 and 100.
    """
    score = (
        severity.score * SEVERITY_WEIGHT
        + impact.overall_impact * IMPACT_WEIGHT
        + confidence * CONFIDENCE_WEIGHT
        + exploitability.score * EXPLOITABILITY_WEIGHT
    )

    return max(0.0, min(100.0, round(score, 1)))


def determine_priority(score: float) -> tuple[str, str]:
    """
    Map a final score to priority level and label.

    Returns (priority_code, priority_label).
    """
    if score >= 80:
        return PRIORITY_P0, SEVERITY_CRITICAL
    elif score >= 60:
        return PRIORITY_P1, SEVERITY_HIGH
    elif score >= 40:
        return PRIORITY_P2, SEVERITY_MEDIUM
    elif score >= 20:
        return PRIORITY_P3, SEVERITY_LOW
    else:
        return PRIORITY_P4, SEVERITY_INFO


def build_scoring_summary(
    severity: SeverityResult,
    impact: ImpactResult,
    exploitability: ExploitabilityResult,
    confidence: float,
    final_score: float,
    priority: str,
    priority_label: str,
) -> str:
    """Build a human-readable scoring breakdown."""
    parts = []
    parts.append(f"=== SCORING BREAKDOWN ===")
    parts.append(f"Severity:        {severity.score:.0f}/100 ({severity.level})")
    parts.append(f"Impact:          {impact.overall_impact:.0f}/100")
    parts.append(f"  - User:        {impact.user_impact:.0f}")
    parts.append(f"  - System:      {impact.system_impact:.0f}")
    parts.append(f"  - Business:    {impact.business_impact:.0f}")
    parts.append(f"Confidence:      {confidence:.0f}/100")
    parts.append(f"Exploitability:  {exploitability.score:.0f}/100")
    parts.append(f"  - Vector:      {exploitability.attack_vector}")
    parts.append(f"  - Complexity:  {exploitability.complexity}")
    parts.append(f"")
    parts.append(f"Final Score:     {final_score:.0f}/100")
    parts.append(f"Priority:        {priority} ({priority_label})")
    parts.append(f"")
    parts.append(f"Weights: Severity {SEVERITY_WEIGHT:.0%} + Impact {IMPACT_WEIGHT:.0%} + "
                 f"Confidence {CONFIDENCE_WEIGHT:.0%} + Exploitability {EXPLOITABILITY_WEIGHT:.0%}")
    return "\n".join(parts)


def create_scored_finding(
    finding_id: str,
    claim_id: str,
    original_claim: str,
    source_agent: str,
    claim_type: str,
    truth_value: str,
    confidence: float,
    severity: SeverityResult,
    impact: ImpactResult,
    exploitability: ExploitabilityResult,
) -> ScoredFinding:
    """
    Create a fully scored finding from all engine outputs.
    """
    final_score = calculate_final_score(
        severity, impact, confidence, exploitability
    )
    priority, priority_label = determine_priority(final_score)

    summary = build_scoring_summary(
        severity, impact, exploitability,
        confidence, final_score, priority, priority_label,
    )

    return ScoredFinding(
        finding_id=finding_id,
        claim_id=claim_id,
        original_claim=original_claim,
        source_agent=source_agent,
        claim_type=claim_type,
        truth_value=truth_value,
        confidence=confidence,
        severity=severity,
        impact=impact,
        exploitability=exploitability,
        final_score=final_score,
        priority=priority,
        priority_label=priority_label,
        scoring_summary=summary,
    )


def score_findings(
    verified_findings: list,
    evidence: list = None,
) -> List[ScoredFinding]:
    """
    Score a list of verified findings.

    Only scores findings with truth_value TRUE or LIKELY_TRUE
    (we don't prioritize false/uncertain claims).

    Returns findings sorted by final_score descending (highest priority first).
    """
    from app.engines.severity_engine import calculate_severity
    from app.engines.impact_engine import calculate_impact
    from app.engines.exploitability_engine import calculate_exploitability
    from app.models.claim import Claim

    scored = []

    for vf in verified_findings:
        # Only score findings that are true or likely true
        if vf.truth_value not in ("TRUE", "LIKELY_TRUE"):
            continue

        # Create a Claim object from the verified finding for engine input
        claim = Claim(
            claim_id=vf.claim_id,
            source_agent=vf.source_agent,
            claim_type=vf.claim_type,
            category=_infer_category(vf.claim_type),
            statement=vf.original_claim,
            target_files=[],
            candidate_evidence=[],
            verification_required=True,
        )

        # Run all scoring engines
        severity = calculate_severity(claim)
        impact = calculate_impact(claim)
        exploitability = calculate_exploitability(claim)

        # Create scored finding
        scored_finding = create_scored_finding(
            finding_id=vf.finding_id,
            claim_id=vf.claim_id,
            original_claim=vf.original_claim,
            source_agent=vf.source_agent,
            claim_type=vf.claim_type,
            truth_value=vf.truth_value,
            confidence=vf.confidence,
            severity=severity,
            impact=impact,
            exploitability=exploitability,
        )

        scored.append(scored_finding)

    # Sort by final score descending
    scored.sort(key=lambda f: f.final_score, reverse=True)

    print(f"  [PriorityEngine] Scored {len(scored)} findings "
          f"(filtered from {len(verified_findings)} verified).")

    return scored


def _infer_category(claim_type: str) -> str:
    """Infer category from claim type."""
    from app.models.claim import CLAIM_CATEGORIES
    for category, types in CLAIM_CATEGORIES.items():
        if claim_type in types:
            return category
    return "unknown"
