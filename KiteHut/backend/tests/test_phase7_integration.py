"""
Phase 7 Integration Test Harness.

Tests: Root Cause, Recommendations, Blast Radius, Effort, Action Plan, Health Score.

Run: cd backend && python -m tests.test_phase7_integration
"""

from app.models.scored_finding import (
    ScoredFinding, SeverityResult, ImpactResult, ExploitabilityResult,
)
from app.engines.root_cause_engine import analyze_root_causes
from app.engines.recommendation_engine import generate_recommendations
from app.engines.effort_engine import estimate_effort_and_impact
from app.engines.action_plan_engine import generate_action_plan
from app.engines.health_score_engine import calculate_health_score
from app.services.action_intelligence_service import generate_action_intelligence


def _make_finding(
    fid="f1", claim_type="hardcoded_secret", statement="Hardcoded secret",
    priority="P0", final_score=92, severity="CRITICAL", severity_score=95,
    confidence=90,
):
    return ScoredFinding(
        finding_id=fid, claim_id=f"c{fid[1:]}", original_claim=statement,
        source_agent="security_agent", claim_type=claim_type,
        truth_value="TRUE", confidence=confidence,
        severity=SeverityResult(level=severity, score=severity_score, reasoning=""),
        impact=ImpactResult(user_impact=70, system_impact=90, business_impact=85,
                           overall_impact=83, reasoning=""),
        exploitability=ExploitabilityResult(score=85, attack_vector="network",
                                           complexity="low", reasoning=""),
        final_score=final_score, priority=priority, priority_label=severity,
    )


def _print(test_num, name, passed, details=""):
    icon = "[PASS]" if passed else "[FAIL]"
    print()
    print("=" * 60)
    print("  Test %d: %s %s" % (test_num, name, icon))
    print("=" * 60)
    if details:
        print(details)
    return passed


# ============================================================
# TEST 1: Root Cause groups related findings
# ============================================================

def test_1_root_cause_grouping():
    findings = [
        _make_finding("f1", "missing_authentication", "No auth", "P0", 90),
        _make_finding("f2", "missing_authorization", "No authz", "P1", 75),
        _make_finding("f3", "weak_input_validation", "No validation", "P1", 70),
    ]
    groups = analyze_root_causes(findings)
    passed = len(groups) >= 1 and any(g.finding_count >= 2 for g in groups)
    details = "  Groups: %d\n  Grouped findings: %s" % (
        len(groups), [g.finding_count for g in groups])
    return _print(1, "Root Cause Grouping", passed, details)


# ============================================================
# TEST 2: Recommendations generated for known types
# ============================================================

def test_2_recommendations():
    findings = [
        _make_finding("f1", "hardcoded_secret", "Secret in config"),
        _make_finding("f2", "missing_tests", "No tests"),
    ]
    recs = generate_recommendations(findings)
    passed = len(recs) == 2 and all(r.title for r in recs)
    details = "  Recommendations: %d\n  Titles: %s" % (
        len(recs), [r.title[:40] for r in recs])
    return _print(2, "Fix Recommendations", passed, details)


# ============================================================
# TEST 3: Effort estimation
# ============================================================

def test_3_effort_estimation():
    findings = [
        _make_finding("f1", "hardcoded_secret", "Secret"),
        _make_finding("f2", "missing_authentication", "No auth"),
    ]
    effort = estimate_effort_and_impact(findings, [], [])
    passed = (
        len(effort) == 2
        and effort[0]["effort"] == "LOW"  # hardcoded_secret
        and effort[1]["effort"] == "HIGH"  # missing_authentication
    )
    details = "  Effort: %s" % [(e["finding_id"], e["effort"]) for e in effort]
    return _print(3, "Effort Estimation", passed, details)


# ============================================================
# TEST 4: Action plan NOW/NEXT/LATER
# ============================================================

def test_4_action_plan():
    findings = [
        _make_finding("f1", "hardcoded_secret", "Secret", "P0", 92),
        _make_finding("f2", "missing_authentication", "No auth", "P1", 80),
        _make_finding("f3", "large_function", "Big func", "P2", 45),
        _make_finding("f4", "naming_issue", "Bad names", "P3", 25),
    ]
    effort = estimate_effort_and_impact(findings, [], [])
    recs = generate_recommendations(findings)
    plan = generate_action_plan(findings, effort, recs)
    passed = (
        plan.now_count == 2
        and plan.next_count == 1
        and plan.later_count == 1
        and plan.total_actions == 4
    )
    details = "  NOW: %d, NEXT: %d, LATER: %d\n  Total: %d" % (
        plan.now_count, plan.next_count, plan.later_count, plan.total_actions)
    return _print(4, "Action Plan Grouping", passed, details)


# ============================================================
# TEST 5: Health score calculation
# ============================================================

def test_5_health_score():
    findings = [
        _make_finding("f1", "hardcoded_secret", "Secret", "P0", 92, "CRITICAL", 95),
        _make_finding("f2", "missing_tests", "No tests", "P2", 45, "MEDIUM", 50),
    ]
    health = calculate_health_score(findings, repository_id=1, analysis_id=1)
    passed = (
        0 <= health.overall_score <= 100
        and health.health_level in ("Excellent", "Good", "Fair", "Poor", "Critical")
        and health.total_findings == 2
        and health.critical_findings == 1
    )
    details = "  Score: %.0f/100 (%s)\n  Findings: %d, Critical: %d\n  Security: %.0f, Testing: %.0f" % (
        health.overall_score, health.health_level,
        health.total_findings, health.critical_findings,
        health.security_score.score, health.testing_score.score)
    return _print(5, "Health Score", passed, details)


# ============================================================
# TEST 6: Health levels correct
# ============================================================

def test_6_health_levels():
    cases = [
        ([], "Excellent"),  # No findings = 100
        ([_make_finding("f1", "naming_issue", "Names", "P4", 10)], "Excellent"),
    ]
    all_pass = True
    details_parts = []
    for findings, expected in cases:
        h = calculate_health_score(findings)
        ok = h.health_level == expected
        if not ok:
            all_pass = False
        details_parts.append("  %d findings -> %s (expected %s) %s" % (
            len(findings), h.health_level, expected, "OK" if ok else "FAIL"))
    return _print(6, "Health Level Classification", all_pass, "\n".join(details_parts))


# ============================================================
# TEST 7: Full pipeline
# ============================================================

def test_7_full_pipeline():
    findings = [
        _make_finding("f1", "hardcoded_secret", "Secret", "P0", 92),
        _make_finding("f2", "missing_authentication", "No auth", "P0", 88),
        _make_finding("f3", "missing_tests", "No tests", "P2", 45),
        _make_finding("f4", "large_function", "Big func", "P3", 30),
    ]
    result = generate_action_intelligence(
        scored_findings=findings,
        repository_id=1,
        analysis_id=1,
    )
    passed = (
        "root_causes" in result
        and "recommendations" in result
        and "action_plan" in result
        and "health" in result
        and result["action_plan"].total_actions == 4
    )
    details = "  Root causes: %d\n  Recommendations: %d\n  Health: %.0f (%s)" % (
        len(result["root_causes"]),
        len(result["recommendations"]),
        result["health"].overall_score,
        result["health"].health_level,
    )
    return _print(7, "Full Phase 7 Pipeline", passed, details)


# ============================================================
# TEST 8: Recommendation has fix steps
# ============================================================

def test_8_recommendation_fix_steps():
    findings = [_make_finding("f1", "hardcoded_secret", "Secret")]
    recs = generate_recommendations(findings)
    passed = (
        len(recs) == 1
        and len(recs[0].fix_steps) >= 3
        and recs[0].effort == "LOW"
        and recs[0].confidence >= 90
    )
    details = "  Steps: %d\n  Effort: %s\n  Confidence: %.0f" % (
        len(recs[0].fix_steps), recs[0].effort, recs[0].confidence)
    return _print(8, "Recommendation Fix Steps", passed, details)


# ============================================================
# Run all tests
# ============================================================

def main():
    print()
    print("#" * 60)
    print("  PHASE 7 INTEGRATION TESTS")
    print("  Testing: Root Cause, Recommendations, Action Plan, Health")
    print("#" * 60)

    results = []
    tests = [
        ("Root Cause Grouping", test_1_root_cause_grouping),
        ("Fix Recommendations", test_2_recommendations),
        ("Effort Estimation", test_3_effort_estimation),
        ("Action Plan Grouping", test_4_action_plan),
        ("Health Score", test_5_health_score),
        ("Health Levels", test_6_health_levels),
        ("Full Pipeline", test_7_full_pipeline),
        ("Recommendation Fix Steps", test_8_recommendation_fix_steps),
    ]

    for name, fn in tests:
        try:
            results.append((name, fn()))
        except Exception as e:
            print("\n[CRASH] %s: %s" % (name, e))
            import traceback
            traceback.print_exc()
            results.append((name, False))

    print()
    print("#" * 60)
    print("  TEST SUMMARY")
    print("#" * 60)
    passed = sum(1 for _, p in results if p)
    total = len(results)
    for name, result in results:
        print("  %s %s" % ("[PASS]" if result else "[FAIL]", name))
    print()
    print("  Total: %d/%d passed" % (passed, total))
    print("#" * 60)
    print()
    return passed == total


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
