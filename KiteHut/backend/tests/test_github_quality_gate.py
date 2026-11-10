"""
Unit Tests for GitHub Quality Gate Evaluator (PRD Section 48).
"""

from app.github.models.github_models import QualityGateRule
from app.github.quality_gate import QualityGateEvaluator
from app.intelligence.models.findings import Finding, FindingCategory, FindingSeverity


def test_quality_gate_passes_clean_findings():
    """Verify quality gate passes when there are no blocking violations."""
    evaluator = QualityGateEvaluator(QualityGateRule(max_p0=0, max_p1=0, tests_must_pass=True))

    findings = [
        Finding(
            category=FindingCategory.QUALITY,
            severity=FindingSeverity.LOW,
            confidence=85.0,
            priority="P3",
            title="Minor linting issue",
            description="Variable naming style",
        )
    ]

    result = evaluator.evaluate(findings=findings, tests_passed=True)
    assert result.passed is True
    assert result.p0_count == 0
    assert result.p1_count == 0
    assert len(result.reasons) == 0
    assert "PASS" in result.summary


def test_quality_gate_blocks_p0_and_security_violations():
    """Verify quality gate fails when P0 findings or security limits are exceeded."""
    evaluator = QualityGateEvaluator(QualityGateRule(max_p0=0, max_p1=0, max_security_findings=0))

    findings = [
        Finding(
            category=FindingCategory.SECURITY,
            severity=FindingSeverity.CRITICAL,
            confidence=95.0,
            priority="P0",
            title="Remote Code Execution via eval()",
            description="Unsanitized user input passed directly to eval()",
        )
    ]

    result = evaluator.evaluate(findings=findings, tests_passed=True)
    assert result.passed is False
    assert result.p0_count == 1
    assert result.security_count == 1
    assert len(result.reasons) >= 1
    assert any("P0" in r for r in result.reasons)


def test_quality_gate_blocks_on_test_failures():
    """Verify quality gate fails when automated tests do not pass."""
    evaluator = QualityGateEvaluator(QualityGateRule(tests_must_pass=True))

    result = evaluator.evaluate(findings=[], tests_passed=False)
    assert result.passed is False
    assert any("test suite failed" in r for r in result.reasons)
