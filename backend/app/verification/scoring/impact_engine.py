"""
Impact Scoring Engine for RepoLens.

Calculates estimated business, operational, and architectural impact (0.0-100.0).
"""

from app.intelligence.models.findings import Finding, FindingCategory, FindingSeverity


class ImpactEngine:
    """Evaluates blast radius and operational impact of a finding."""

    def compute_impact(self, finding: Finding) -> float:
        """Calculate impact score 0.0 to 100.0."""
        # Category base impact
        category_weights = {
            FindingCategory.SECURITY: 90.0,
            FindingCategory.ARCHITECTURE: 70.0,
            FindingCategory.API: 65.0,
            FindingCategory.CONFIGURATION: 60.0,
            FindingCategory.TESTING: 55.0,
            FindingCategory.QUALITY: 40.0,
            FindingCategory.DEPENDENCY: 50.0,
            FindingCategory.CODE_REVIEW: 45.0,
        }
        base_impact = category_weights.get(finding.category, 50.0)

        # Severity adjustment
        severity_multipliers = {
            FindingSeverity.CRITICAL: 1.15,
            FindingSeverity.HIGH: 1.0,
            FindingSeverity.MEDIUM: 0.85,
            FindingSeverity.LOW: 0.65,
            FindingSeverity.INFO: 0.40,
        }
        mult = severity_multipliers.get(finding.severity, 1.0)
        score = base_impact * mult

        # Blast radius adjustment based on affected files
        if finding.affected_files and len(finding.affected_files) > 1:
            score += min(15.0, len(finding.affected_files) * 3.0)

        return min(100.0, max(0.0, round(score, 1)))
