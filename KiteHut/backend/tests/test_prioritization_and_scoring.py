"""
Unit Tests for Scoring and Prioritization Engine (Layer 6).
"""

from app.intelligence.models.findings import Finding, FindingCategory, FindingSeverity
from app.verification.models.priority import Priority
from app.verification.scoring.exploitability_engine import ExploitabilityEngine
from app.verification.scoring.impact_engine import ImpactEngine
from app.verification.scoring.prioritization_engine import PrioritizationEngine


def test_scoring_formula_calculation():
    """Verify that PrioritizationEngine implements the exact 4-factor PRD formula."""
    engine = PrioritizationEngine()

    finding = Finding(
        category=FindingCategory.SECURITY,
        severity=FindingSeverity.CRITICAL,
        title="SQL Injection in auth service",
        description="Dynamic SQL query allows remote auth bypass",
        file_path="src/auth.py",
        line_number=42,
        confidence=90.0,
    )

    breakdown = engine.calculate_score(finding)

    # Check weights: 35% Sev, 30% Impact, 20% Conf, 15% Exploit
    expected_score = (
        (breakdown.severity_score * 0.35)
        + (breakdown.impact_score * 0.30)
        + (breakdown.confidence_score * 0.20)
        + (breakdown.exploitability_score * 0.15)
    )
    expected_score = round(expected_score, 1)

    assert breakdown.final_score == expected_score
    assert breakdown.severity_score == 100.0
    assert breakdown.final_score >= 80.0
    assert breakdown.priority == Priority.P0
    assert "Severity(100.0×35%)" in breakdown.explanation


def test_priority_tier_distribution():
    """Verify mapping of various findings across P0, P1, P2, P3, P4 tiers."""
    engine = PrioritizationEngine()

    # 1. P0 finding: Critical Security
    f_p0 = Finding(
        category=FindingCategory.SECURITY,
        severity=FindingSeverity.CRITICAL,
        title="Hardcoded AWS Root Key",
        description="sk_live_ credential",
        confidence=100.0,
    )
    b_p0 = engine.calculate_score(f_p0)
    assert b_p0.priority == Priority.P0

    # 2. P2 finding: Medium Quality
    f_p2 = Finding(
        category=FindingCategory.QUALITY,
        severity=FindingSeverity.MEDIUM,
        title="Moderate complexity function",
        description="Branching logic exceeds threshold",
        confidence=70.0,
    )
    b_p2 = engine.calculate_score(f_p2)
    assert b_p2.priority in {Priority.P2, Priority.P3}

    # 3. P4 finding: Low Info
    f_p4 = Finding(
        category=FindingCategory.QUALITY,
        severity=FindingSeverity.INFO,
        title="Variable name length",
        description="Short variable name 'x'",
        confidence=40.0,
    )
    b_p4 = engine.calculate_score(f_p4)
    assert b_p4.priority in {Priority.P3, Priority.P4}
    assert b_p4.final_score < 40.0
