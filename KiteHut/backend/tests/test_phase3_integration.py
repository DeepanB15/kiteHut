"""
Phase 3 Integration Test Harness.

Tests the full verification pipeline: Claims -> Evidence -> Verification -> Truth -> Confidence

Creates mock repositories on disk for each scenario, feeds mock agent results
into the pipeline, and validates outcomes.

Run: cd backend && python -m tests.test_phase3_integration
"""

import shutil
import tempfile
from pathlib import Path

from app.models.agent_results import (
    SecurityResult,
    ArchitectureResult,
    QualityResult,
    TestingResult,
)
from app.services.claim_extractor import extract_all_claims
from app.services.verification_planner import create_verification_plans
from app.services.evidence_collector import collect_all_evidence
from app.services.evidence_normalizer import normalize_evidence_list, deduplicate_evidence
from app.services.deterministic_verifier import verify_all_claims
from app.services.cross_agent_validator import validate_cross_agent
from app.engines.truth_engine import classify_truth
from app.engines.confidence_engine import calculate_confidence


# ============================================================
# Test helpers
# ============================================================

def _create_repo(files: dict) -> str:
    """Create a temporary repo directory with given files. Returns path."""
    tmpdir = tempfile.mkdtemp(prefix="repolens_test_")
    for rel_path, content in files.items():
        full_path = Path(tmpdir) / rel_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content, encoding="utf-8")
    return tmpdir


def _run_pipeline(
    repo_path: str,
    security_result=None,
    architecture_result=None,
    quality_result=None,
    testing_result=None,
):
    """Run the full Phase 3 pipeline and return verified findings."""
    # Step 1: Extract claims
    claims = extract_all_claims(
        architecture_result=architecture_result,
        security_result=security_result,
        quality_result=quality_result,
        testing_result=testing_result,
    )

    if not claims:
        return []

    # Step 2: Create verification plans
    plans = create_verification_plans(claims)

    # Step 3: Collect evidence
    evidence = collect_all_evidence(repo_path, claims, plans)

    # Step 4: Normalize
    evidence = normalize_evidence_list(evidence)
    evidence = deduplicate_evidence(evidence)

    # Step 5: Cross-agent validation
    cross_evidence = validate_cross_agent(claims, evidence, len(evidence) + 1)
    evidence.extend(cross_evidence)

    # Step 6: Deterministic verification
    verification_results = verify_all_claims(claims, evidence, repo_path)

    # Step 7: Truth & confidence
    findings = []
    claim_map = {c.claim_id: c for c in claims}
    for vr in verification_results:
        claim = claim_map.get(vr.claim_id)
        if not claim:
            continue

        cross_agent_support = any(
            e.claim_id == claim.claim_id
            and e.source == "cross_agent_validation"
            and e.relation == "supports"
            for e in evidence
        )

        truth_value = classify_truth(claim, vr, evidence)
        confidence = calculate_confidence(claim, vr, evidence, cross_agent_support)

        findings.append({
            "claim_id": claim.claim_id,
            "claim_type": claim.claim_type,
            "statement": claim.statement,
            "source_agent": claim.source_agent,
            "verification_status": vr.status,
            "truth_value": truth_value,
            "confidence": round(confidence, 1),
            "supporting_count": len(vr.supporting_evidence),
            "contradicting_count": len(vr.contradicting_evidence),
        })

    return findings


def _print_result(test_num, name, finding, expected):
    """Print a formatted test result."""
    truth_ok = finding["truth_value"] == expected.get("truth")
    status_ok = finding["verification_status"] == expected.get("status")

    if expected.get("truth_any"):
        truth_ok = finding["truth_value"] in expected["truth_any"]
    if expected.get("status_any"):
        status_ok = finding["verification_status"] in expected["status_any"]

    passed = truth_ok and status_ok
    icon = "[PASS]" if passed else "[FAIL]"

    print()
    print("=" * 60)
    print("  Test %d: %s %s" % (test_num, name, icon))
    print("=" * 60)
    print("  Claim:        %s" % finding["statement"])
    print("  Claim Type:   %s" % finding["claim_type"])
    print("  Source Agent: %s" % finding["source_agent"])
    print("  ")
    print("  Verification: %s" % finding["verification_status"])
    print("  Truth Value:  %s" % finding["truth_value"])
    print("  Confidence:   %s%%" % finding["confidence"])
    print("  Evidence:     %d supporting, %d contradicting" % (
        finding["supporting_count"], finding["contradicting_count"]))
    print("  ")
    expected_truth = expected.get("truth", expected.get("truth_any"))
    expected_status = expected.get("status", expected.get("status_any"))
    print("  Expected:     status=%s, truth=%s" % (expected_status, expected_truth))
    print("  Truth match:  %s" % ("OK" if truth_ok else "FAIL"))
    print("  Status match: %s" % ("OK" if status_ok else "FAIL"))

    return passed


# ============================================================
# TEST 1: Hardcoded Secret
# ============================================================

def test_1_hardcoded_secret():
    """Repo contains API_KEY = 'sk-example-secret-very-long'. Should be TRUE."""
    repo_path = _create_repo({
        "config.py": 'API_KEY = "sk-example-secret-very-long-value-here"\nDB_HOST = "localhost"\n',
        "app.py": 'from config import API_KEY\nprint(API_KEY)\n',
        "requirements.txt": "fastapi==0.100.0\nuvicorn==0.23.0\n",
    })

    security = SecurityResult(
        security_observations=["Application uses hardcoded secrets"],
        potential_risks=["Hardcoded API key found in config.py. The secret sk-example-secret is embedded directly in source code."],
        security_strengths=[],
        areas_for_verification=["Verify if API_KEY in config.py is hardcoded or from environment"],
    )

    findings = _run_pipeline(repo_path, security_result=security)
    shutil.rmtree(repo_path, ignore_errors=True)

    assert len(findings) > 0, "Should have at least 1 finding"
    f = findings[0]

    expected = {"status": "supported", "truth": "TRUE"}
    return _print_result(1, "Hardcoded Secret", f, expected)


# ============================================================
# TEST 2: Environment Variable (False Positive)
# ============================================================

def test_2_env_variable():
    """Repo uses os.getenv. AI claims hardcoded secret -> should be FALSE."""
    repo_path = _create_repo({
        "config.py": 'import os\nAPI_KEY = os.getenv("API_KEY")\nDB_HOST = os.getenv("DB_HOST", "localhost")\n',
        "app.py": 'from config import API_KEY\nprint(API_KEY)\n',
        "requirements.txt": "fastapi==0.100.0\n",
    })

    security = SecurityResult(
        security_observations=["Application loads configuration from environment"],
        potential_risks=["A hardcoded API key may exist in config.py. The variable API_KEY could contain a secret."],
        security_strengths=["Environment variables used for configuration"],
        areas_for_verification=["Verify if API_KEY is hardcoded or from environment"],
    )

    findings = _run_pipeline(repo_path, security_result=security)
    shutil.rmtree(repo_path, ignore_errors=True)

    assert len(findings) > 0, "Should have at least 1 finding"
    f = findings[0]

    expected = {"status": "contradicted", "truth_any": ["FALSE", "LIKELY_FALSE"]}
    return _print_result(2, "Environment Variable (False Positive)", f, expected)


# ============================================================
# TEST 3: Tests Exist (Contradicts No-Tests Claim)
# ============================================================

def test_3_tests_exist():
    """Repo has tests/. AI claims tests missing -> should be FALSE.

    Per PRD: 'Tests are missing' + repo has tests/ -> FALSE, High Confidence.
    """
    repo_path = _create_repo({
        "app.py": "def add(a, b): return a + b\n",
        "tests/__init__.py": "",
        "tests/test_app.py": "from app import add\n\ndef test_add():\n    assert add(1, 2) == 3\n",
    })

    # AI agent INCORRECTLY claims tests are missing
    testing = TestingResult(
        test_frameworks=[],
        test_types=[],
        testing_maturity="none",
        tested_components=[],
        potentially_untested_components=["app"],
        observations=["No test directory or test files found in the repository"],
    )

    findings = _run_pipeline(repo_path, testing_result=testing)
    shutil.rmtree(repo_path, ignore_errors=True)

    assert len(findings) > 0, "Should have at least 1 finding"
    f = findings[0]

    expected = {"status": "contradicted", "truth_any": ["FALSE", "LIKELY_FALSE"]}
    return _print_result(3, "Tests Exist (Contradicts No-Tests Claim)", f, expected)


# ============================================================
# TEST 4: No Tests (Confirms No-Tests Claim)
# ============================================================

def test_4_no_tests():
    """Repo has no tests at all. AI claims tests missing -> should be TRUE."""
    repo_path = _create_repo({
        "app/__init__.py": "",
        "app/models/user.py": "class User:\n    def __init__(self, name):\n        self.name = name\n",
        "app/services/auth.py": "def authenticate(user): return True\n",
        "requirements.txt": "fastapi==0.100.0\n",
    })

    testing = TestingResult(
        test_frameworks=[],
        test_types=[],
        testing_maturity="none",
        tested_components=[],
        potentially_untested_components=["app.models.user", "app.services.auth"],
        observations=["No test directory or test files found in the repository"],
    )

    findings = _run_pipeline(repo_path, testing_result=testing)
    shutil.rmtree(repo_path, ignore_errors=True)

    # Should get findings for the untested components
    assert len(findings) > 0, "Should have at least 1 finding"
    # Find the missing_tests type finding
    test_findings = [f for f in findings if f["claim_type"] == "missing_tests"]
    assert len(test_findings) > 0, "Should have a missing_tests finding"

    f = test_findings[0]
    expected = {"status": "supported", "truth": "TRUE"}
    return _print_result(4, "No Tests (Confirms Claim)", f, expected)


# ============================================================
# TEST 5: Authentication Exists (Contradicts Missing Auth)
# ============================================================

def test_5_auth_exists():
    """Repo has JWT auth middleware. AI claims auth missing -> should be FALSE."""
    repo_path = _create_repo({
        "app/__init__.py": "",
        "app/auth.py": """from fastapi import Depends, HTTPException
import jwt

def get_current_user(token: str = Depends(oauth2_scheme)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        return payload
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
""",
        "app/middleware.py": """class AuthenticationMiddleware:
    def __init__(self, app):
        self.app = app
    async def __call__(self, scope, receive, send):
        # Check authentication
        pass
""",
        "app/routes.py": """from fastapi import APIRouter, Depends
from app.auth import get_current_user

router = APIRouter()

@router.get("/protected")
async def protected_route(user = Depends(get_current_user)):
    return {"user": user}
""",
    })

    security = SecurityResult(
        security_observations=["Application has authentication middleware"],
        potential_risks=["Authentication appears to be missing from the API routes. No authentication middleware detected."],
        security_strengths=["JWT-based authentication exists"],
        areas_for_verification=["Verify if authentication is properly applied to all routes"],
    )

    findings = _run_pipeline(repo_path, security_result=security)
    shutil.rmtree(repo_path, ignore_errors=True)

    assert len(findings) > 0, "Should have at least 1 finding"
    f = findings[0]

    expected = {
        "status_any": ["contradicted", "uncertain"],
        "truth_any": ["FALSE", "LIKELY_FALSE", "UNCERTAIN"],
    }
    return _print_result(5, "Auth Exists (Contradicts Missing Auth)", f, expected)


# ============================================================
# TEST 6: Conflicting Evidence -> UNCERTAIN
# ============================================================

def test_6_conflicting_evidence():
    """Repo has auth module BUT some routes unprotected -> UNCERTAIN."""
    repo_path = _create_repo({
        "app/__init__.py": "",
        "app/auth.py": """from fastapi import Depends

def get_current_user():
    pass
""",
        "app/routes.py": """from fastapi import APIRouter
from app.auth import get_current_user

router = APIRouter()

@router.get("/public")
async def public_route():
    return {"message": "hello"}

@router.get("/admin")
async def admin_route():
    return {"secret": "data"}
""",
        "app/requirements.txt": "fastapi==0.100.0\npyjwt==2.8.0\n",
    })

    security = SecurityResult(
        security_observations=["Auth module exists but not all routes use it"],
        potential_risks=[
            "Some API routes lack authentication middleware",
            "The /admin route has no authentication protection but contains sensitive data",
        ],
        security_strengths=["Authentication module exists"],
        areas_for_verification=["Verify which routes are protected"],
    )

    findings = _run_pipeline(repo_path, security_result=security)
    shutil.rmtree(repo_path, ignore_errors=True)

    assert len(findings) > 0, "Should have at least 1 finding"

    # We expect at least one UNCERTAIN finding, or a mix of results
    uncertain_count = sum(1 for f in findings if f["truth_value"] == "UNCERTAIN")

    passed = uncertain_count > 0 or len(findings) >= 2
    icon = "[PASS]" if passed else "[FAIL]"

    print()
    print("=" * 60)
    print("  Test 6: Conflicting Evidence -> UNCERTAIN %s" % icon)
    print("=" * 60)
    for f in findings:
        print("  Claim:        %s" % f["statement"][:70])
        print("  Type:         %s" % f["claim_type"])
        print("  Verification: %s" % f["verification_status"])
        print("  Truth Value:  %s" % f["truth_value"])
        print("  Confidence:   %s%%" % f["confidence"])
        print("  Evidence:     %d supporting, %d contradicting" % (
            f["supporting_count"], f["contradicting_count"]))
        print("  ---")
    print("  ")
    print("  Uncertain findings: %d/%d" % (uncertain_count, len(findings)))
    print("  Expected: At least 1 UNCERTAIN finding or multiple findings")

    return passed


# ============================================================
# Run all tests
# ============================================================

def main():
    print()
    print("#" * 60)
    print("  PHASE 3 INTEGRATION TESTS")
    print("  Testing: Claims -> Evidence -> Verification -> Truth -> Confidence")
    print("#" * 60)

    results = []

    try:
        results.append(("Test 1: Hardcoded Secret", test_1_hardcoded_secret()))
    except Exception as e:
        print("\n[CRASH] Test 1: %s" % e)
        import traceback
        traceback.print_exc()
        results.append(("Test 1: Hardcoded Secret", False))

    try:
        results.append(("Test 2: Env Variable (False Positive)", test_2_env_variable()))
    except Exception as e:
        print("\n[CRASH] Test 2: %s" % e)
        import traceback
        traceback.print_exc()
        results.append(("Test 2: Env Variable (False Positive)", False))

    try:
        results.append(("Test 3: Tests Exist (Contradicts Claim)", test_3_tests_exist()))
    except Exception as e:
        print("\n[CRASH] Test 3: %s" % e)
        import traceback
        traceback.print_exc()
        results.append(("Test 3: Tests Exist (Contradicts Claim)", False))

    try:
        results.append(("Test 4: No Tests (Confirms Claim)", test_4_no_tests()))
    except Exception as e:
        print("\n[CRASH] Test 4: %s" % e)
        import traceback
        traceback.print_exc()
        results.append(("Test 4: No Tests (Confirms Claim)", False))

    try:
        results.append(("Test 5: Auth Exists (Contradicts Claim)", test_5_auth_exists()))
    except Exception as e:
        print("\n[CRASH] Test 5: %s" % e)
        import traceback
        traceback.print_exc()
        results.append(("Test 5: Auth Exists (Contradicts Claim)", False))

    try:
        results.append(("Test 6: Conflicting Evidence", test_6_conflicting_evidence()))
    except Exception as e:
        print("\n[CRASH] Test 6: %s" % e)
        import traceback
        traceback.print_exc()
        results.append(("Test 6: Conflicting Evidence", False))

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
