"""
Prioritization and Scoring Engine for RepoLens.

Implements the PRD Layer 6 explainable 4-factor scoring and P0-P4 priority mapping.
"""

from app.intelligence.models.findings import Finding, FindingSeverity
from app.verification.models.priority import Priority, ScoreBreakdown
from app.verification.scoring.exploitability_engine import ExploitabilityEngine
from app.verification.scoring.impact_engine import ImpactEngine


class PrioritizationEngine:
    """Computes explainable composite finding scores and priority tiers."""

    def __init__(
        self,
        impact_engine: ImpactEngine = None,
        exploitability_engine: ExploitabilityEngine = None,
    ):
        self.impact_engine = impact_engine or ImpactEngine()
        self.exploitability_engine = exploitability_engine or ExploitabilityEngine()

    def calculate_score(
        self,
        finding: Finding,
        confidence_override: float = None,
    ) -> ScoreBreakdown:
        """Calculate weighted composite score and determine priority tier."""
        # 1. Severity Score (0-100)
        severity_map = {
            FindingSeverity.CRITICAL: 100.0,
            FindingSeverity.HIGH: 75.0,
            FindingSeverity.MEDIUM: 50.0,
            FindingSeverity.LOW: 25.0,
            FindingSeverity.INFO: 10.0,
        }
        severity_score = severity_map.get(finding.severity, 50.0)

        # 2. Impact Score (0-100)
        impact_score = self.impact_engine.compute_impact(finding)

        # 3. Confidence Score (0-100)
        confidence_score = confidence_override if confidence_override is not None else finding.confidence

        # 4. Exploitability Score (0-100)
        exploitability_score = self.exploitability_engine.compute_exploitability(finding)

        # PRD Section 25 Weighted Formula:
        # Final Score = Severity * 35% + Impact * 30% + Confidence * 20% + Exploitability * 15%
        final_score = (
            (severity_score * 0.35)
            + (impact_score * 0.30)
            + (confidence_score * 0.20)
            + (exploitability_score * 0.15)
        )
        final_score = round(min(100.0, max(0.0, final_score)), 1)

        # Map to Priority Level:
        # 80-100 -> P0
        # 60-79  -> P1
        # 40-59  -> P2
        # 20-39  -> P3
        # 0-19   -> P4
        if final_score >= 80.0:
            priority = Priority.P0
        elif final_score >= 60.0:
            priority = Priority.P1
        elif final_score >= 40.0:
            priority = Priority.P2
        elif final_score >= 20.0:
            priority = Priority.P3
        else:
            priority = Priority.P4

        explanation = (
            f"Score {final_score}/100 [{priority.value}] = "
            f"Severity({severity_score}×35%) + Impact({impact_score}×30%) + "
            f"Confidence({confidence_score}×20%) + Exploitability({exploitability_score}×15%)"
        )

        return ScoreBreakdown(
            severity_score=severity_score,
            impact_score=impact_score,
            confidence_score=confidence_score,
            exploitability_score=exploitability_score,
            final_score=final_score,
            priority=priority,
            explanation=explanation,
        )
