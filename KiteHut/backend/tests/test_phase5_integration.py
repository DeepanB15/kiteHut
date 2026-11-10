"""
Phase 5 Integration Test Harness.

Tests the persistence layer, history APIs, and comparison engine.
Uses SQLite in-memory for fast, isolated tests.

Run: cd backend && python -m tests.test_phase5_integration
"""

import os
import tempfile
from datetime import datetime, timezone

# Use SQLite for testing (no Docker needed)
os.environ["DATABASE_URL"] = "sqlite:///test_repolens.db"

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.db_models.repository import Repository
from app.db_models.analysis_run import AnalysisRun
from app.db_models.finding import Finding
from app.db_models.evidence import Evidence
from app.services.persistence_service import (
    find_or_create_repository,
    create_analysis_run,
    update_analysis_run_status,
    persist_scored_findings,
    persist_analysis,
    _generate_fingerprint,
)
from app.services.comparison_engine import compare_analyses, get_previous_run
from app.models.scored_finding import (
    ScoredFinding,
    SeverityResult,
    ImpactResult,
    ExploitabilityResult,
)
from app.models.evidence import Evidence as EvidenceModel


# ============================================================
# Test database setup
# ============================================================

TEST_DB_PATH = "test_repolens.db"
TEST_DB_URL = f"sqlite:///{TEST_DB_PATH}"

test_engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
TestSession = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


def setup_test_db():
    """Create all tables for testing."""
    Base.metadata.create_all(bind=test_engine)


def teardown_test_db():
    """Drop all tables and cleanup."""
    Base.metadata.drop_all(bind=test_engine)
    test_engine.dispose()
    try:
        if os.path.exists(TEST_DB_PATH):
            os.remove(TEST_DB_PATH)
    except PermissionError:
        pass


def get_test_session():
    """Get a test database session."""
    db = TestSession()
    try:
        yield db
    finally:
        db.close()


# ============================================================
# Test helpers
# ============================================================

def _make_scored_finding(
    finding_id="f_001",
    claim_id="c_001",
    claim_type="hardcoded_secret",
    statement="Hardcoded API key in config.py",
    truth_value="TRUE",
    confidence=90.0,
    severity_level="CRITICAL",
    severity_score=95.0,
    final_score=92.0,
    priority="P0",
):
    """Create a ScoredFinding for testing."""
    return ScoredFinding(
        finding_id=finding_id,
        claim_id=claim_id,
        original_claim=statement,
        source_agent="security_agent",
        claim_type=claim_type,
        truth_value=truth_value,
        confidence=confidence,
        severity=SeverityResult(level=severity_level, score=severity_score, reasoning=""),
        impact=ImpactResult(
            user_impact=70, system_impact=90, business_impact=85,
            overall_impact=83.0, reasoning="",
        ),
        exploitability=ExploitabilityResult(
            score=85, attack_vector="network", complexity="low", reasoning="",
        ),
        final_score=final_score,
        priority=priority,
        priority_label=severity_level,
        scoring_summary="",
    )


def _make_evidence(
    evidence_id="ev_001",
    claim_id="c_001",
    file_path="config.py",
    content="API_KEY = 'secret123'",
    relation="supports",
):
    """Create an Evidence model for testing."""
    return EvidenceModel(
        evidence_id=evidence_id,
        claim_id=claim_id,
        source="file_scan",
        type="source_code",
        file_path=file_path,
        line_start=1,
        line_end=1,
        content=content,
        relation=relation,
        strength="strong",
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
# TEST 1: Repository CRUD
# ============================================================

def test_1_repository_crud():
    """Test finding and creating repositories."""
    db = TestSession()
    try:
        repo = find_or_create_repository(
            db,
            github_url="https://github.com/test/repo",
            owner="test",
            name="repo",
        )
        db.flush()

        assert repo.id is not None
        assert repo.github_url == "https://github.com/test/repo"
        assert repo.owner == "test"
        assert repo.name == "repo"

        # Find again (should return same)
        repo2 = find_or_create_repository(
            db,
            github_url="https://github.com/test/repo",
            owner="test",
            name="repo",
        )
        assert repo.id == repo2.id

        db.rollback()
        passed = True
        details = "  Repository ID: %d\n  Found again: same ID" % repo.id
    except Exception as e:
        passed = False
        details = "  Error: %s" % str(e)
        db.rollback()
    finally:
        db.close()

    return _print_result(1, "Repository CRUD", passed, details)


# ============================================================
# TEST 2: Analysis Run lifecycle
# ============================================================

def test_2_analysis_run_lifecycle():
    """Test creating and updating analysis runs."""
    db = TestSession()
    try:
        repo = find_or_create_repository(
            db, "https://github.com/test/run", "test", "run"
        )
        run = create_analysis_run(db, repo.id)
        db.flush()

        assert run.id is not None
        assert run.status == "PENDING"

        update_analysis_run_status(db, run, "RUNNING")
        assert run.status == "RUNNING"

        update_analysis_run_status(db, run, "COMPLETED", total_findings=5)
        assert run.status == "COMPLETED"
        assert run.total_findings == 5
        assert run.completed_at is not None
        assert run.duration_seconds is not None

        db.rollback()
        passed = True
        details = (
            "  Run ID: %d\n"
            "  Status: %s\n"
            "  Findings: %d\n"
            "  Duration: %.1fs" % (
                run.id, run.status, run.total_findings, run.duration_seconds
            )
        )
    except Exception as e:
        passed = False
        details = "  Error: %s" % str(e)
        db.rollback()
    finally:
        db.close()

    return _print_result(2, "Analysis Run Lifecycle", passed, details)


# ============================================================
# TEST 3: Persist findings
# ============================================================

def test_3_persist_findings():
    """Test persisting scored findings with evidence."""
    db = TestSession()
    try:
        repo = find_or_create_repository(
            db, "https://github.com/test/findings", "test", "findings"
        )
        run = create_analysis_run(db, repo.id)
        update_analysis_run_status(db, run, "RUNNING")
        db.flush()

        sf1 = _make_scored_finding(
            finding_id="f1", claim_id="c1",
            claim_type="hardcoded_secret",
            statement="Hardcoded API key",
            priority="P0",
        )
        sf2 = _make_scored_finding(
            finding_id="f2", claim_id="c2",
            claim_type="missing_tests",
            statement="No tests found",
            priority="P2",
            severity_level="MEDIUM",
            severity_score=50.0,
            final_score=45.0,
        )

        evidence = [_make_evidence(claim_id="c1")]

        saved = persist_scored_findings(db, run, [sf1, sf2], evidence)
        db.commit()

        assert len(saved) == 2
        assert saved[0].fingerprint is not None
        assert saved[0].priority == "P0"

        # Verify evidence was saved
        ev_count = db.query(Evidence).filter(
            Evidence.finding_id == saved[0].id
        ).count()
        assert ev_count == 1

        passed = True
        details = (
            "  Findings saved: %d\n"
            "  Fingerprint: %s\n"
            "  Priority: %s\n"
            "  Evidence count: %d" % (
                len(saved), saved[0].fingerprint,
                saved[0].priority, ev_count
            )
        )
    except Exception as e:
        passed = False
        details = "  Error: %s" % str(e)
        import traceback
        traceback.print_exc()
        db.rollback()
    finally:
        db.close()

    return _print_result(3, "Persist Findings", passed, details)


# ============================================================
# TEST 4: Full persist_analysis workflow
# ============================================================

def test_4_persist_analysis_workflow():
    """Test the complete persistence workflow."""
    db = TestSession()
    try:
        sf = _make_scored_finding(
            finding_id="f_full", claim_id="c_full",
            claim_type="hardcoded_secret",
            statement="Hardcoded secret in app.py",
            priority="P1",
        )
        evidence = [_make_evidence(claim_id="c_full", file_path="app.py")]

        repo, run, findings = persist_analysis(
            db=db,
            repository_url="https://github.com/test/full",
            owner="test",
            name="full",
            scored_findings=[sf],
            all_evidence=evidence,
        )

        assert repo.id is not None
        assert run.id is not None
        assert run.status == "COMPLETED"
        assert len(findings) == 1
        assert findings[0].priority == "P1"

        passed = True
        details = (
            "  Repository: #%d %s/%s\n"
            "  Run: #%d [%s]\n"
            "  Findings: %d\n"
            "  Duration: %.1fs" % (
                repo.id, repo.owner, repo.name,
                run.id, run.status,
                len(findings),
                run.duration_seconds or 0,
            )
        )
    except Exception as e:
        passed = False
        details = "  Error: %s" % str(e)
        import traceback
        traceback.print_exc()
        db.rollback()
    finally:
        db.close()

    return _print_result(4, "Full Persist Analysis Workflow", passed, details)


# ============================================================
# TEST 5: Fingerprint generation
# ============================================================

def test_5_fingerprint_generation():
    """Test fingerprint generation for cross-run comparison."""
    fp1 = _generate_fingerprint("hardcoded_secret", "security_risk", ["config.py"])
    fp2 = _generate_fingerprint("hardcoded_secret", "security_risk", ["config.py"])
    fp3 = _generate_fingerprint("hardcoded_secret", "security_risk", ["app.py"])
    fp4 = _generate_fingerprint("missing_tests", "testing_issue")

    passed = (
        fp1 == fp2
        and fp1 != fp3
        and "config.py" in fp1
        and "missing_tests" in fp4
    )
    details = (
        "  FP1: %s\n"
        "  FP2: %s (same=%s)\n"
        "  FP3: %s (different=%s)\n"
        "  FP4: %s" % (
            fp1, fp2, fp1 == fp2,
            fp3, fp1 != fp3,
            fp4,
        )
    )
    return _print_result(5, "Fingerprint Generation", passed, details)


# ============================================================
# TEST 6: Comparison engine - new/resolved/existing
# ============================================================

def test_6_comparison_engine():
    """Test comparison engine detects new, resolved, and existing findings."""
    db = TestSession()
    try:
        # Run 1: 3 findings
        sf1 = _make_scored_finding(
            finding_id="f1", claim_id="c1",
            claim_type="hardcoded_secret", statement="Secret in config",
            priority="P0",
        )
        sf2 = _make_scored_finding(
            finding_id="f2", claim_id="c2",
            claim_type="missing_tests", statement="No tests",
            priority="P2", severity_level="MEDIUM", severity_score=50,
            final_score=45,
        )
        sf3 = _make_scored_finding(
            finding_id="f3", claim_id="c3",
            claim_type="large_function", statement="Function too long",
            priority="P3", severity_level="LOW", severity_score=30,
            final_score=28,
        )
        _, run1, _ = persist_analysis(
            db, "https://github.com/test/compare", "test", "compare",
            [sf1, sf2, sf3],
        )

        # Run 2: 2 findings (secret fixed, new missing auth added, tests still missing)
        sf4 = _make_scored_finding(
            finding_id="f4", claim_id="c4",
            claim_type="missing_tests", statement="No tests",
            priority="P2", severity_level="MEDIUM", severity_score=50,
            final_score=45,
        )
        sf5 = _make_scored_finding(
            finding_id="f5", claim_id="c5",
            claim_type="missing_authentication", statement="Auth missing",
            priority="P1", severity_level="HIGH", severity_score=85,
            final_score=80,
        )
        _, run2, _ = persist_analysis(
            db, "https://github.com/test/compare", "test", "compare",
            [sf4, sf5],
        )

        # Compare
        result = compare_analyses(db, run1.id, run2.id)

        passed = (
            result.summary.new >= 1  # missing_authentication is new
            and result.summary.resolved >= 1  # hardcoded_secret is resolved
            and result.summary.existing >= 1  # missing_tests is existing
        )
        details = (
            "  Run 1 findings: 3 (secret, tests, large_function)\n"
            "  Run 2 findings: 2 (tests, missing_auth)\n"
            "  \n"
            "  Comparison:\n"
            "    New:      %d (expected: missing_auth)\n"
            "    Resolved: %d (expected: hardcoded_secret)\n"
            "    Existing: %d (expected: missing_tests)\n"
            "    Changed:  %d\n"
            "  \n"
            "  Match: %s" % (
                result.summary.new,
                result.summary.resolved,
                result.summary.existing,
                result.summary.changed,
                "OK" if passed else "FAIL"
            )
        )
    except Exception as e:
        passed = False
        details = "  Error: %s" % str(e)
        import traceback
        traceback.print_exc()
        db.rollback()
    finally:
        db.close()

    return _print_result(6, "Comparison Engine", passed, details)


# ============================================================
# TEST 7: Previous run detection
# ============================================================

def test_7_previous_run_detection():
    """Test finding the previous analysis run."""
    db = TestSession()
    try:
        sf = _make_scored_finding()
        _, run1, _ = persist_analysis(
            db, "https://github.com/test/prev", "test", "prev", [sf]
        )
        _, run2, _ = persist_analysis(
            db, "https://github.com/test/prev", "test", "prev", [sf]
        )

        prev = get_previous_run(db, run2.repository_id, run2.id)

        passed = prev is not None and prev.id == run1.id
        details = (
            "  Run 1: #%d\n"
            "  Run 2: #%d\n"
            "  Previous of Run 2: #%s\n"
            "  Correct: %s" % (
                run1.id, run2.id,
                prev.id if prev else "None",
                "OK" if passed else "FAIL"
            )
        )
    except Exception as e:
        passed = False
        details = "  Error: %s" % str(e)
        db.rollback()
    finally:
        db.close()

    return _print_result(7, "Previous Run Detection", passed, details)


# ============================================================
# TEST 8: Finding with priority change
# ============================================================

def test_8_priority_change_detection():
    """Test detection of priority changes between runs."""
    db = TestSession()
    try:
        # Run 1: finding at P1
        sf1 = _make_scored_finding(
            finding_id="f_prio", claim_id="c_prio",
            claim_type="hardcoded_secret", statement="Secret found",
            priority="P1", final_score=70,
        )
        _, run1, _ = persist_analysis(
            db, "https://github.com/test/prio", "test", "prio", [sf1]
        )

        # Run 2: same finding escalated to P0
        sf2 = _make_scored_finding(
            finding_id="f_prio2", claim_id="c_prio",
            claim_type="hardcoded_secret", statement="Secret found",
            priority="P0", final_score=90,
        )
        _, run2, _ = persist_analysis(
            db, "https://github.com/test/prio", "test", "prio", [sf2]
        )

        result = compare_analyses(db, run1.id, run2.id)

        passed = result.summary.changed >= 1
        details = (
            "  Run 1: hardcoded_secret at P1 (score 70)\n"
            "  Run 2: hardcoded_secret at P0 (score 90)\n"
            "  Changed findings: %d\n"
            "  Match: %s" % (
                result.summary.changed,
                "OK" if passed else "FAIL"
            )
        )
    except Exception as e:
        passed = False
        details = "  Error: %s" % str(e)
        db.rollback()
    finally:
        db.close()

    return _print_result(8, "Priority Change Detection", passed, details)


# ============================================================
# TEST 9: Error handling - failed analysis
# ============================================================

def test_9_error_handling():
    """Test that failed analyses are persisted correctly."""
    db = TestSession()
    try:
        repo, run, findings = persist_analysis(
            db=db,
            repository_url="https://github.com/test/error",
            owner="test",
            name="error",
            scored_findings=[],
            error_message="Clone failed: timeout",
        )

        passed = (
            run.status == "FAILED"
            and run.error_message == "Clone failed: timeout"
            and len(findings) == 0
        )
        details = (
            "  Status: %s\n"
            "  Error: %s\n"
            "  Findings: %d\n"
            "  Match: %s" % (
                run.status, run.error_message,
                len(findings),
                "OK" if passed else "FAIL"
            )
        )
    except Exception as e:
        passed = False
        details = "  Error: %s" % str(e)
        db.rollback()
    finally:
        db.close()

    return _print_result(9, "Error Handling - Failed Analysis", passed, details)


# ============================================================
# TEST 10: Database statistics
# ============================================================

def test_10_database_statistics():
    """Test querying database for statistics."""
    db = TestSession()
    try:
        # Create some data
        sf = _make_scored_finding()
        persist_analysis(
            db, "https://github.com/test/stats", "test", "stats", [sf]
        )
        persist_analysis(
            db, "https://github.com/test/stats", "test", "stats", [sf]
        )

        # Query
        repo_count = db.query(Repository).count()
        run_count = db.query(AnalysisRun).count()
        finding_count = db.query(Finding).count()

        passed = repo_count >= 1 and run_count >= 2
        details = (
            "  Repositories: %d\n"
            "  Analysis Runs: %d\n"
            "  Total Findings: %d\n"
            "  Match: %s" % (
                repo_count, run_count, finding_count,
                "OK" if passed else "FAIL"
            )
        )
    except Exception as e:
        passed = False
        details = "  Error: %s" % str(e)
        db.rollback()
    finally:
        db.close()

    return _print_result(10, "Database Statistics", passed, details)


# ============================================================
# Run all tests
# ============================================================

def main():
    print()
    print("#" * 60)
    print("  PHASE 5 INTEGRATION TESTS")
    print("  Testing: Persistence, History, Comparison")
    print("#" * 60)

    setup_test_db()

    results = []

    tests = [
        ("Repository CRUD", test_1_repository_crud),
        ("Analysis Run Lifecycle", test_2_analysis_run_lifecycle),
        ("Persist Findings", test_3_persist_findings),
        ("Full Persist Workflow", test_4_persist_analysis_workflow),
        ("Fingerprint Generation", test_5_fingerprint_generation),
        ("Comparison Engine", test_6_comparison_engine),
        ("Previous Run Detection", test_7_previous_run_detection),
        ("Priority Change Detection", test_8_priority_change_detection),
        ("Error Handling", test_9_error_handling),
        ("Database Statistics", test_10_database_statistics),
    ]

    for name, test_fn in tests:
        try:
            results.append((name, test_fn()))
        except Exception as e:
            print("\n[CRASH] %s: %s" % (name, e))
            import traceback
            traceback.print_exc()
            results.append((name, False))

    teardown_test_db()

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
