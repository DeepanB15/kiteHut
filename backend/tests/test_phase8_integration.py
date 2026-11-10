"""
Phase 8 Integration Test Harness.

Tests: production configuration, repository URL hardening,
async analysis jobs, health/readiness endpoints, and the job API.

Uses an isolated SQLite database via a temp file.

Run (harness):  cd backend && python -m tests.test_phase8_integration
Run (pytest):   cd backend && pytest tests/test_phase8_integration.py -q
"""

import atexit
import os
import tempfile

# ------------------------------------------------------------
# Isolated test environment (must happen before importing app)
# ENVIRONMENT=testing -> config does not load .env.development
# ------------------------------------------------------------
_tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmp_db.close()

os.environ["ENVIRONMENT"] = "testing"
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp_db.name}"
os.environ["RATE_LIMIT_PER_MINUTE"] = "0"  # disable rate limiting in tests

from fastapi.testclient import TestClient  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.main import app  # noqa: E402
from app.services.git_service import (  # noqa: E402
    InvalidRepositoryURL,
    validate_github_repository_url,
)
from app.services.job_service import (  # noqa: E402
    create_job,
    get_job,
    update_job,
)

client = TestClient(app)


def _cleanup():
    try:
        os.unlink(_tmp_db.name)
    except OSError:
        pass


atexit.register(_cleanup)


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
# TEST 1: Configuration loads environment-aware settings
# ============================================================

def test_1_configuration():
    checks = [
        settings.ENVIRONMENT == "testing",
        settings.is_testing,
        "http://localhost:5173" in settings.cors_origins,
        "github.com" in settings.allowed_repository_hosts,
        settings.RATE_LIMIT_PER_MINUTE == 0,
        settings.DATABASE_URL.startswith("sqlite"),
        settings.API_PORT == 8000,
    ]
    passed = all(checks)
    details = "  ENVIRONMENT=%s\n  CORS=%s\n  Allowed hosts=%s\n  Rate limit=%d" % (
        settings.ENVIRONMENT,
        settings.cors_origins,
        settings.allowed_repository_hosts,
        settings.RATE_LIMIT_PER_MINUTE,
    )
    return _print(1, "Production Configuration", passed, details)


# ============================================================
# TEST 2: Valid repository URL parsing
# ============================================================

def test_2_valid_urls():
    cases = [
        ("https://github.com/octocat/Hello-World", ("octocat", "Hello-World")),
        ("https://github.com/owner/repo.git", ("owner", "repo")),
        ("https://www.github.com/owner/repo", ("owner", "repo")),
        ("https://github.com/owner/repo/", ("owner", "repo")),
    ]
    results = []
    for url, expected in cases:
        try:
            result = validate_github_repository_url(url)
            results.append(result == expected)
        except InvalidRepositoryURL:
            results.append(False)

    passed = all(results)
    details = "\n".join(
        "  %s -> %s" % (url, "OK" if ok else "FAIL")
        for url, ok in zip([c[0] for c in cases], results)
    )
    return _print(2, "Valid Repository URLs", passed, details)


# ============================================================
# TEST 3: Invalid / unsafe repository URLs rejected
# ============================================================

def test_3_invalid_urls():
    bad_urls = [
        "ssh://git@github.com/owner/repo.git",        # wrong scheme
        "git://github.com/owner/repo.git",            # wrong scheme
        "https://github.com/only-one-part",           # missing repo name
        "https://github.com/",                        # empty path
        "https://evil.com/owner/repo",                # non-allowed host
        "https://github.com/user:pass@github.com/owner/repo",  # credentials
        "https://github.com/owner/repo/extra",        # too many parts
        "https://github.com/ow ner/repo",            # invalid characters
        "https://github.com/" + "a" * 3000,          # too long
    ]
    rejected = 0
    for url in bad_urls:
        try:
            validate_github_repository_url(url)
        except InvalidRepositoryURL:
            rejected += 1

    passed = rejected == len(bad_urls)
    details = "  Rejected %d/%d unsafe URLs" % (rejected, len(bad_urls))
    return _print(3, "Unsafe Repository URLs Rejected", passed, details)


# ============================================================
# TEST 4: Job creation and status updates
# ============================================================

def test_4_job_lifecycle():
    job = create_job("https://github.com/octocat/Hello-World")
    try:
        created_ok = (
            job.job_id is not None
            and job.status == "PENDING"
            and job.current_stage == "PENDING"
        )

        updated = update_job(
            job.job_id,
            status="CLONING",
            stage="CLONING",
            message="Cloning repository...",
        )
        stage_ok = updated.status == "CLONING" and updated.current_stage == "CLONING"

        fetched = get_job(job.job_id)
        fetch_ok = fetched is not None and fetched.status == "CLONING"

        completed = update_job(
            job.job_id,
            status="COMPLETED",
            stage="COMPLETED",
            analysis_run_id=42,
        )
        completed_ok = (
            completed.status == "COMPLETED"
            and completed.completed_at is not None
            and completed.analysis_run_id == 42
        )

        passed = created_ok and stage_ok and fetch_ok and completed_ok
        details = "  Created: %s\n  Stage: %s\n  Fetch: %s\n  Completed: %s" % (
            created_ok, stage_ok, fetch_ok, completed_ok,
        )
    finally:
        db = __import__("app.core.database", fromlist=["SessionLocal"]).SessionLocal()
        try:
            job_model = db.get(
                __import__("app.db_models.analysis_job", fromlist=["AnalysisJob"]).AnalysisJob,
                job.job_id,
            )
            if job_model:
                db.delete(job_model)
                db.commit()
        finally:
            db.close()

    return _print(4, "Job Lifecycle", passed, details)


# ============================================================
# TEST 5: Health & readiness endpoints
# ============================================================

def test_5_health_endpoints():
    health = client.get("/health")
    health_ok = (
        health.status_code == 200
        and health.json().get("status") == "healthy"
    )

    ready = client.get("/ready")
    ready_body = ready.json()
    ready_ok = (
        ready.status_code == 200
        and ready_body.get("status") in ("ready", "degraded")
        and ready_body.get("services", {}).get("database") == "healthy"
        and "ollama" in ready_body.get("services", {})
    )

    request_id = health.headers.get("x-request-id")
    request_id_ok = bool(request_id)

    passed = health_ok and ready_ok and request_id_ok
    details = (
        "  /health -> %s (%s)\n"
        "  /ready  -> %s services=%s\n"
        "  X-Request-ID present: %s" % (
            health.status_code,
            health.json().get("status"),
            ready.status_code,
            ready_body.get("services"),
            request_id_ok,
        )
    )
    return _print(5, "Health & Readiness Endpoints", passed, details)


# ============================================================
# TEST 6: Job API — missing job returns 404
# ============================================================

def test_6_job_api_missing():
    response = client.get("/api/v1/jobs/does-not-exist")
    passed = response.status_code == 404
    details = "  GET /api/v1/jobs/does-not-exist -> %d" % response.status_code
    return _print(6, "Job API 404", passed, details)


# ============================================================
# TEST 7: Job API — unsafe URL rejected with 400
# ============================================================

def test_7_analyze_rejects_unsafe_url():
    response = client.post("/api/v1/analyze", json={
        "repository_url": "https://evil.com/owner/repo"
    })
    body = response.json()
    passed = response.status_code == 400 and "detail" in body
    details = "  POST /api/v1/analyze (evil.com) -> %d: %s" % (
        response.status_code, body.get("detail"),
    )
    return _print(7, "Analyze Rejects Unsafe URL", passed, details)


# ============================================================
# TEST 8: Job API — malformed payload returns 422
# ============================================================

def test_8_analyze_rejects_malformed_payload():
    response = client.post("/api/v1/analyze", json={
        "repository_url": "not-a-url"
    })
    passed = response.status_code == 422
    details = "  POST /api/v1/analyze (not-a-url) -> %d" % response.status_code
    return _print(8, "Analyze Rejects Malformed Payload", passed, details)


# ============================================================
# Run all tests
# ============================================================

def main():
    print()
    print("#" * 60)
    print("  PHASE 8 INTEGRATION TESTS")
    print("  Testing: Config, Security, Jobs, Health, API")
    print("#" * 60)

    results = []
    tests = [
        ("Production Configuration", test_1_configuration),
        ("Valid Repository URLs", test_2_valid_urls),
        ("Unsafe Repository URLs", test_3_invalid_urls),
        ("Job Lifecycle", test_4_job_lifecycle),
        ("Health & Readiness", test_5_health_endpoints),
        ("Job API 404", test_6_job_api_missing),
        ("Analyze Unsafe URL", test_7_analyze_rejects_unsafe_url),
        ("Analyze Malformed", test_8_analyze_rejects_malformed_payload),
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
    _cleanup()
    exit(0 if success else 1)