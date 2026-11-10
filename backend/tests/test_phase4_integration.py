"""
Phase 4 Integration Test Harness.

Tests the scoring and prioritization pipeline:
  Verified Finding -> Severity -> Impact -> Exploitability -> Final Score -> Priority

Run: cd backend && python -m tests.test_phase4_integration
"""

import shutil
import tempfile
from pathlib import Path

from app.models.verified_finding import VerifiedFinding
from app.models.claim import Claim
from app.engines.severity_engine import calculate_severity
from app.engines.impact_engine import calculate_impact
from app.engines.exploitability_engine import calculate_exploitability
from app.engines.priority_engine import (
    calculate_final_score,
    determine_priority,
    score_findings,
    create_scored_finding,
)
from app.models.scored_finding import (
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
# Test helpers
# ============================================================

def _make_verified_finding(
    finding_id="finding_001",
    claim_id="claim_001",
    statement="Hardcoded API key found",
    source_agent="security_agent",
    claim_type="hardcoded_secret",
    truth_value="TRUE",
    confidence=90.0,
):
    """Create a VerifiedFinding for testing."""
    return VerifiedFinding(
        finding_id=finding_id,
        claim_id=claim_id,
        original_claim=statement,
        source_agent=source_agent,
        claim_type=claim_type,
        truth_value=truth_value,
        confidence=confidence,
        supporting_evidence_count=2,
        contradicting_evidence_count=0,
        verification_summary="Test summary",
        verification_methods=["secret_pattern_scan"],
        cross_agent_support=False,
    )


def _make_claim(
    claim_id="claim_001",
    claim_type="hardcoded_secret",
    category="security_risk",
    statement="Hardcoded API key found",
):
    """Create a Claim for testing."""
    return Claim(
        claim_id=claim_id,
        source_agent="security_agent",
        claim_type=claim_type,
        category=category,
        statement=statement,
        target_files=[],
        candidate_evidence=[],
        verification_required=True,
    )


def _print_result(test_num, name, passed, details=""):
    """Print a formatted test result."""
    icon = "[PASS]" if passed else "[FAIL]"
    print()
    print("=" * 60)
    print("  Test %d: %s %s" % (test_num, name, icon))
    print("=" * 60)
    if details:
        print(details)
    return passed


# ============================================================
# TEST 1: Hardcoded Secret gets CRITICAL severity
# ============================================================

def test_1_critical_severity():
    """Hardcoded API key should score CRITICAL severity."""
    claim = _make_claim(claim_type="hardcoded_secret", category="security_risk")
    severity = calculate_severity(claim)

    passed = (
        severity.level == "CRITICAL"
        and severity.score >= 80
    )
    details = (
        "  Claim Type:  hardcoded_secret\n"
        "  Severity:    %s (%.0f/100)\n"
        "  Expected:    CRITICAL (>=80)\n"
        "  Match:       %s" % (
            severity.level, severity.score,
            "OK" if passed else "FAIL"
        )
    )
    return _print_result(1, "Critical Severity for Hardcoded Secret", passed, details)


# ============================================================
# TEST 2: Naming issue gets LOW severity
# ============================================================

def test_2_low_severity():
    """Naming issue should score LOW severity."""
    claim = _make_claim(
        claim_type="naming_issue",
        category="quality_issue",
        statement="Variable naming is inconsistent",
    )
    severity = calculate_severity(claim)

    passed = (
        severity.level in ("LOW", "INFO")
        and severity.score < 40
    )
    details = (
        "  Claim Type:  naming_issue\n"
        "  Severity:    %s (%.0f/100)\n"
        "  Expected:    LOW/INFO (<40)\n"
        "  Match:       %s" % (
            severity.level, severity.score,
            "OK" if passed else "FAIL"
        )
    )
    return _print_result(2, "Low Severity for Naming Issue", passed, details)


# ============================================================
# TEST 3: Missing Authentication has high impact
# ============================================================

def test_3_high_impact():
    """Missing authentication should have high system + business impact."""
    claim = _make_claim(
        claim_type="missing_authentication",
        category="security_risk",
        statement="Authentication is missing from API routes",
    )
    impact = calculate_impact(claim)

    passed = (
        impact.system_impact >= 80
        and impact.business_impact >= 80
        and impact.overall_impact >= 70
    )
    details = (
        "  Claim Type:     missing_authentication\n"
        "  User Impact:    %.0f\n"
        "  System Impact:  %.0f\n"
        "  Business Impact: %.0f\n"
        "  Overall Impact: %.0f\n"
        "  Expected:       system>=80, business>=80, overall>=70\n"
        "  Match:          %s" % (
            impact.user_impact, impact.system_impact,
            impact.business_impact, impact.overall_impact,
            "OK" if passed else "FAIL"
        )
    )
    return _print_result(3, "High Impact for Missing Authentication", passed, details)


# ============================================================
# TEST 4: Naming issue has low exploitability
# ============================================================

def test_4_low_exploitability():
    """Naming issue should have very low exploitability."""
    claim = _make_claim(
        claim_type="naming_issue",
        category="quality_issue",
        statement="Variable naming is inconsistent",
    )
    exploit = calculate_exploitability(claim)

    passed = exploit.score <= 20
    details = (
        "  Claim Type:  naming_issue\n"
        "  Exploitability: %.0f/100\n"
        "  Vector:     %s\n"
        "  Complexity: %s\n"
        "  Expected:   <=20\n"
        "  Match:      %s" % (
            exploit.score, exploit.attack_vector,
            exploit.complexity,
            "OK" if passed else "FAIL"
        )
    )
    return _print_result(4, "Low Exploitability for Naming Issue", passed, details)


# ============================================================
# TEST 5: Final score formula correctness
# ============================================================

def test_5_score_formula():
    """Verify the scoring formula: severity*35% + impact*30% + confidence*20% + exploit*15%."""
    from app.engines.severity_engine import SeverityResult
    from app.engines.impact_engine import ImpactResult
    from app.engines.exploitability_engine import ExploitabilityResult

    severity = SeverityResult(level="CRITICAL", score=95, reasoning="")
    impact = ImpactResult(
        user_impact=70, system_impact=90, business_impact=85,
        overall_impact=83.0, reasoning="",
    )
    exploitability = ExploitabilityResult(
        score=85, attack_vector="network", complexity="low", reasoning="",
    )
    confidence = 94.0

    final = calculate_final_score(severity, impact, confidence, exploitability)

    # Expected: 95*0.35 + 83*0.30 + 94*0.20 + 85*0.15
    #         = 33.25 + 24.9 + 18.8 + 12.75 = 89.7
    expected = 95 * 0.35 + 83.0 * 0.30 + 94 * 0.20 + 85 * 0.15

    passed = abs(final - expected) < 1.0
    details = (
        "  Severity:  95 x 35%% = %.2f\n"
        "  Impact:    83 x 30%% = %.2f\n"
        "  Confidence: 94 x 20%% = %.2f\n"
        "  Exploit:   85 x 15%% = %.2f\n"
        "  Expected:  %.1f\n"
        "  Actual:    %.1f\n"
        "  Match:     %s" % (
            95 * 0.35, 83.0 * 0.30, 94 * 0.20, 85 * 0.15,
            expected, final,
            "OK" if passed else "FAIL"
        )
    )
    return _print_result(5, "Score Formula Correctness", passed, details)


# ============================================================
# TEST 6: Priority mapping
# ============================================================

def test_6_priority_mapping():
    """Verify priority level mapping."""
    cases = [
        (90, "P0", "CRITICAL"),
        (70, "P1", "HIGH"),
        (50, "P2", "MEDIUM"),
        (30, "P3", "LOW"),
        (10, "P4", "INFO"),
    ]

    all_pass = True
    details_parts = []
    for score, expected_priority, expected_label in cases:
        priority, label = determine_priority(score)
        ok = priority == expected_priority and label == expected_label
        if not ok:
            all_pass = False
        details_parts.append(
            "  Score %.0f -> %s (%s) %s" % (
                score, priority, label, "OK" if ok else "FAIL"
            )
        )

    return _print_result(6, "Priority Mapping", all_pass, "\n".join(details_parts))


# ============================================================
# TEST 7: Full pipeline — Hardcoded Secret scores CRITICAL
# ============================================================

def test_7_full_pipeline_critical():
    """Full pipeline: hardcoded secret -> TRUE -> scores P0/CRITICAL."""
    vf = _make_verified_finding(
        claim_type="hardcoded_secret",
        statement="Hardcoded API key found in config.py",
        truth_value="TRUE",
        confidence=94.0,
    )

    scored = score_findings([vf])

    assert len(scored) == 1
    f = scored[0]

    passed = (
        f.priority == "P0"
        and f.priority_label == "CRITICAL"
        and f.final_score >= 80
        and f.severity.level == "CRITICAL"
    )
    details = (
        "  Finding:    %s\n"
        "  Severity:   %s (%.0f)\n"
        "  Impact:     %.0f\n"
        "  Exploit:    %.0f\n"
        "  Confidence: %.0f\n"
        "  Final:      %.0f/100\n"
        "  Priority:   %s (%s)\n"
        "  Expected:   P0/CRITICAL, score>=80\n"
        "  Match:      %s" % (
            f.claim_type,
            f.severity.level, f.severity.score,
            f.impact.overall_impact,
            f.exploitability.score,
            f.confidence,
            f.final_score,
            f.priority, f.priority_label,
            "OK" if passed else "FAIL"
        )
    )
    return _print_result(7, "Full Pipeline: Hardcoded Secret -> P0 CRITICAL", passed, details)


# ============================================================
# TEST 8: Full pipeline — Naming Issue scores LOW
# ============================================================

def test_8_full_pipeline_low():
    """Full pipeline: naming issue -> TRUE -> scores P3/LOW."""
    vf = _make_verified_finding(
        claim_type="naming_issue",
        statement="Variable naming is inconsistent",
        truth_value="TRUE",
        confidence=80.0,
    )

    scored = score_findings([vf])

    assert len(scored) == 1
    f = scored[0]

    passed = (
        f.priority in ("P3", "P4")
        and f.final_score < 40
    )
    details = (
        "  Finding:    %s\n"
        "  Severity:   %s (%.0f)\n"
        "  Final:      %.0f/100\n"
        "  Priority:   %s (%s)\n"
        "  Expected:   P3/P4, score<40\n"
        "  Match:      %s" % (
            f.claim_type,
            f.severity.level, f.severity.score,
            f.final_score,
            f.priority, f.priority_label,
            "OK" if passed else "FAIL"
        )
    )
    return _print_result(8, "Full Pipeline: Naming Issue -> P3 LOW", passed, details)


# ============================================================
# TEST 9: FALSE findings are filtered out
# ============================================================

def test_9_false_filtered():
    """FALSE/LIKELY_FALSE findings should not be scored."""
    vf_true = _make_verified_finding(
        finding_id="f1", claim_id="c1",
        claim_type="hardcoded_secret",
        truth_value="TRUE", confidence=90,
    )
    vf_false = _make_verified_finding(
        finding_id="f2", claim_id="c2",
        claim_type="missing_tests",
        truth_value="FALSE", confidence=50,
    )
    vf_uncertain = _make_verified_finding(
        finding_id="f3", claim_id="c3",
        claim_type="missing_authentication",
        truth_value="UNCERTAIN", confidence=40,
    )

    scored = score_findings([vf_true, vf_false, vf_uncertain])

    passed = len(scored) == 1 and scored[0].claim_type == "hardcoded_secret"
    details = (
        "  Input: 3 findings (TRUE, FALSE, UNCERTAIN)\n"
        "  Scored: %d findings\n"
        "  Expected: 1 (only TRUE)\n"
        "  Match: %s" % (
            len(scored),
            "OK" if passed else "FAIL"
        )
    )
    return _print_result(9, "FALSE Findings Filtered Out", passed, details)


# ============================================================
# TEST 10: Multiple findings are ranked by score
# ============================================================

def test_10_ranking():
    """Multiple findings should be ranked by final score descending."""
    vf_critical = _make_verified_finding(
        finding_id="f1", claim_id="c1",
        claim_type="hardcoded_secret",
        truth_value="TRUE", confidence=95,
    )
    vf_medium = _make_verified_finding(
        finding_id="f2", claim_id="c2",
        claim_type="large_function",
        statement="Function is too long",
        truth_value="TRUE", confidence=80,
    )
    vf_low = _make_verified_finding(
        finding_id="f3", claim_id="c3",
        claim_type="naming_issue",
        statement="Naming is inconsistent",
        truth_value="LIKELY_TRUE", confidence=70,
    )

    scored = score_findings([vf_critical, vf_medium, vf_low])

    passed = (
        len(scored) == 3
        and scored[0].final_score >= scored[1].final_score
        and scored[1].final_score >= scored[2].final_score
    )
    details = (
        "  Input: 3 findings (hardcoded_secret, large_function, naming_issue)\n"
        "  Ranked output:\n"
        "    1. %s: %.0f/100 (%s)\n"
        "    2. %s: %.0f/100 (%s)\n"
        "    3. %s: %.0f/100 (%s)\n"
        "  Descending order: %s" % (
            scored[0].claim_type, scored[0].final_score, scored[0].priority,
            scored[1].claim_type, scored[1].final_score, scored[1].priority,
            scored[2].claim_type, scored[2].final_score, scored[2].priority,
            "OK" if passed else "FAIL"
        )
    )
    return _print_result(10, "Findings Ranked by Score Descending", passed, details)


# ============================================================
# Run all tests
# ============================================================

def main():
    print()
    print("#" * 60)
    print("  PHASE 4 INTEGRATION TESTS")
    print("  Testing: Severity -> Impact -> Exploitability -> Score -> Priority")
    print("#" * 60)

    results = []

    tests = [
        ("Critical Severity", test_1_critical_severity),
        ("Low Severity", test_2_low_severity),
        ("High Impact", test_3_high_impact),
        ("Low Exploitability", test_4_low_exploitability),
        ("Score Formula", test_5_score_formula),
        ("Priority Mapping", test_6_priority_mapping),
        ("Full Pipeline: Secret -> P0", test_7_full_pipeline_critical),
        ("Full Pipeline: Naming -> P3", test_8_full_pipeline_low),
        ("FALSE Filtered Out", test_9_false_filtered),
        ("Ranking Order", test_10_ranking),
    ]

    for name, test_fn in tests:
        try:
            results.append((name, test_fn()))
        except Exception as e:
            print("\n[CRASH] %s: %s" % (name, e))
            import traceback
            traceback.print_exc()
            results.append((name, False))

    # Summary
    print()
    print("#" * 60)
    print("  TEST SUMMARY")
    print("#" * 60)
    passed = sum(1 for _, p in results if p)
    total = len(results)
    for name, result in results:
        icon = "[PASS]" if result else "[FAIL]"
        print("  %s %s" % (icon, name))

    print()
    print("  Total: %d/%d passed" % (passed, total))
    print("#" * 60)
    print()

    return passed == total


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
