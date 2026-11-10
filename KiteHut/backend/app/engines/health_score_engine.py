"""
Repository Health Score Engine.

Calculates an overall health score for the repository based on
findings across all categories.

Score ranges:
  90-100: Excellent
  75-89:  Good
  60-74:  Fair
  40-59:  Poor
  0-39:   Critical
"""

from typing import List

from app.models.scored_finding import ScoredFinding
from app.models.repository_health import RepositoryHealth, CategoryScore


# Health level thresholds
HEALTH_LEVELS = [
    (90, "Excellent"),
    (75, "Good"),
    (60, "Fair"),
    (40, "Poor"),
    (0, "Critical"),
]

# Finding penalty weights by priority
PRIORITY_PENALTY = {
    "P0": 25,
    "P1": 15,
    "P2": 8,
    "P3": 3,
    "P4": 1,
}

# Category weight in overall score
CATEGORY_WEIGHTS = {
    "security_risk": 0.30,
    "architecture_issue": 0.20,
    "quality_issue": 0.25,
    "testing_issue": 0.25,
}


def calculate_health_score(
    scored_findings: List[ScoredFinding],
    repository_id: int = 0,
    analysis_id: int = 0,
) -> RepositoryHealth:
    """
    Calculate repository health score from scored findings.
    """
    # Group findings by category
    categories: dict[str, list[ScoredFinding]] = {}
    for f in scored_findings:
        cat = _infer_category(f.claim_type)
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(f)

    # Calculate category scores
    security = _category_score(categories.get("security_risk", []), "Security")
    architecture = _category_score(categories.get("architecture_issue", []), "Architecture")
    quality = _category_score(categories.get("quality_issue", []), "Quality")
    testing = _category_score(categories.get("testing_issue", []), "Testing")

    # Maintainability is derived from quality + architecture
    maintainability_score = (quality.score + architecture.score) / 2
    maintainability = CategoryScore(
        name="Maintainability",
        score=round(maintainability_score, 1),
        finding_count=quality.finding_count + architecture.finding_count,
        top_issue=quality.top_issue or architecture.top_issue,
    )

    # Overall score (weighted average)
    overall = (
        security.score * CATEGORY_WEIGHTS["security_risk"]
        + architecture.score * CATEGORY_WEIGHTS["architecture_issue"]
        + quality.score * CATEGORY_WEIGHTS["quality_issue"]
        + testing.score * CATEGORY_WEIGHTS["testing_issue"]
    )

    # Determine health level
    health_level = "Critical"
    for threshold, level in HEALTH_LEVELS:
        if overall >= threshold:
            health_level = level
            break

    # Count critical findings
    critical = sum(1 for f in scored_findings if f.priority in ("P0", "P1"))

    summary = _build_health_summary(
        overall, health_level, len(scored_findings), critical,
        security, architecture, quality, testing,
    )

    return RepositoryHealth(
        repository_id=repository_id,
        analysis_id=analysis_id,
        overall_score=round(overall, 1),
        health_level=health_level,
        security_score=security,
        architecture_score=architecture,
        quality_score=quality,
        testing_score=testing,
        maintainability_score=maintainability,
        total_findings=len(scored_findings),
        critical_findings=critical,
        summary=summary,
    )


def _category_score(findings: list[ScoredFinding], name: str) -> CategoryScore:
    """Calculate score for a category. Start at 100, deduct for findings."""
    score = 100.0
    top_issue = ""

    for f in findings:
        penalty = PRIORITY_PENALTY.get(f.priority, 1)
        score -= penalty
        if not top_issue or f.final_score > (findings[0].final_score if findings else 0):
            top_issue = f.original_claim

    score = max(0.0, min(100.0, score))

    return CategoryScore(
        name=name,
        score=round(score, 1),
        finding_count=len(findings),
        top_issue=top_issue[:100] if top_issue else "",
    )


def _infer_category(claim_type: str) -> str:
    """Infer category from claim type."""
    from app.models.claim import CLAIM_CATEGORIES
    for category, types in CLAIM_CATEGORIES.items():
        if claim_type in types:
            return category
    return "quality_issue"


def _build_health_summary(
    overall, level, total, critical,
    security, architecture, quality, testing,
) -> str:
    """Build human-readable health summary."""
    parts = []
    parts.append(f"Repository health is {level} ({overall:.0f}/100).")

    if critical > 0:
        parts.append(f"{critical} critical issues require immediate attention.")

    # Highlight weakest area
    scores = [
        (security.score, "Security"),
        (architecture.score, "Architecture"),
        (quality.score, "Quality"),
        (testing.score, "Testing"),
    ]
    weakest = min(scores, key=lambda x: x[0])
    if weakest[0] < 70:
        parts.append(f"{weakest[1]} is the weakest area at {weakest[0]:.0f}/100.")

    return " ".join(parts)
