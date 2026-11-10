"""
Quality Gate Evaluator for RepoLens (PRD Section 48).
"""

from typing import List, Optional
from app.github.models.github_models import (
    QualityGateCategoryVerdict,
    QualityGateResult,
    QualityGateRule,
)
from app.intelligence.models.findings import Finding, FindingCategory


class QualityGateEvaluator:
    """Evaluates verified findings and test outcomes against repository quality rules."""

    def __init__(self, rule: Optional[QualityGateRule] = None):
        self.rule = rule or QualityGateRule()

    def evaluate(
        self,
        findings: List[Finding],
        tests_passed: bool = True,
        rule_override: Optional[QualityGateRule] = None,
    ) -> QualityGateResult:
        """Evaluate findings against quality gate thresholds."""
        rule = rule_override or self.rule
        reasons: List[str] = []

        # Filter to confident findings above confidence threshold
        active_findings = [
            f for f in findings
            if (f.confidence or 0.0) >= rule.confidence_threshold and (f.truth_status != "FALSE")
        ]

        # 1. Check P0 count
        p0_findings = [f for f in active_findings if f.priority == "P0"]
        p0_count = len(p0_findings)
        if p0_count > rule.max_p0:
            reasons.append(f"Found {p0_count} Critical (P0) finding(s) (threshold: {rule.max_p0}).")

        # 2. Check P1 count
        p1_findings = [f for f in active_findings if f.priority == "P1"]
        p1_count = len(p1_findings)
        if p1_count > rule.max_p1:
            reasons.append(f"Found {p1_count} High (P1) finding(s) (threshold: {rule.max_p1}).")

        # 3. Check Security Findings count
        security_findings = [f for f in active_findings if f.category == FindingCategory.SECURITY]
        security_count = len(security_findings)
        if security_count > rule.max_security_findings:
            reasons.append(f"Found {security_count} Security finding(s) (threshold: {rule.max_security_findings}).")

        # 4. Check Tests Pass Requirement
        if rule.tests_must_pass and not tests_passed:
            reasons.append("Automated test suite failed or introduced regressions.")

        # Compute Category-level verdicts
        category_verdicts = []
        for cat in [FindingCategory.SECURITY, FindingCategory.ARCHITECTURE, FindingCategory.TESTING, FindingCategory.QUALITY]:
            cat_list = [f for f in active_findings if f.category == cat]
            cat_p0_p1 = [f for f in cat_list if f.priority in ("P0", "P1")]
            passed = len(cat_p0_p1) == 0
            if cat == FindingCategory.TESTING and not tests_passed:
                passed = False
            category_verdicts.append(
                QualityGateCategoryVerdict(
                    category=cat.value.capitalize(),
                    passed=passed,
                    findings_count=len(cat_list),
                    message="PASS" if passed else f"FAIL ({len(cat_list)} issues)",
                )
            )

        passed = len(reasons) == 0

        # Construct concise summary description
        if passed:
            summary = "RepoLens Quality Gate: PASS (0 blocking issues)"
        else:
            summary = f"RepoLens Quality Gate: FAILED ({len(reasons)} rule violations: {reasons[0][:60]})"[:140]

        return QualityGateResult(
            passed=passed,
            p0_count=p0_count,
            p1_count=p1_count,
            security_count=security_count,
            tests_passed=tests_passed,
            category_verdicts=category_verdicts,
            reasons=reasons,
            summary=summary,
        )
