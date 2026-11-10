"""
Phase 9 Integration Test Harness.

Tests: PR patch parsing, deterministic scan rules, GitHub webhook
signature verification, /analyze-pr queueing, connection status,
quality gate evaluation, commit status checks, and the full PR
analysis service run (with a fake GitHub client).

Fully hermetic — the job runner is stubbed so no network or clone
happens, and scans run on inline sample code.

Run (harness):  cd backend && python -m tests.test_phase9_integration
Run (pytest):   cd backend && pytest tests/test_phase9_integration.py -q
"""

import atexit
import hashlib
import hmac
import json
import os
import sys
import tempfile

# Windows consoles default to cp1252; our PR comment uses emoji.
# Make sure printed output (harness + pytest) is UTF-8 safe.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ------------------------------------------------------------
# Isolated test environment (must happen before importing app)
# ------------------------------------------------------------
_tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmp_db.close()

os.environ["ENVIRONMENT"] = "testing"
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp_db.name}"
os.environ["RATE_LIMIT_PER_MINUTE"] = "0"
os.environ["GITHUB_WEBHOOK_SECRET"] = "test-webhook-secret"

from fastapi.testclient import TestClient  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.main import app  # noqa: E402
from app.services.pr_scanner import (  # noqa: E402
    ScanFinding,
    parse_added_lines,
    scan_added_content,
)
from app.services.pr_analysis_service import (  # noqa: E402
    build_pr_comment,
    run_pr_analysis,
    _post_status_check,
)
from app.services.job_service import create_job, get_job, update_job  # noqa: E402
from app.engines.quality_gate import evaluate_quality_gate  # noqa: E402

client = TestClient(app)

# Ensure the webhook secret is present regardless of import order
settings.GITHUB_WEBHOOK_SECRET = "test-webhook-secret"
settings.PR_POST_COMMENT = True

# Stub the background runner so tests never touch the network
import app.api.github_routes as github_routes  # noqa: E402
github_routes.start_analysis_job = lambda *args, **kwargs: None  # type: ignore[assignment]


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
# Sample diff
# ============================================================

_SAMPLE_PATCH = """\
@@ -1,5 +1,8 @@
 def load_config():
     # existing context line
     api_key = os.getenv("API_KEY")
+    secret = "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghij"
+    verify = False
+    run_command = eval(user_input)
     return config
"""


# ============================================================
# TEST 1: Patch parser extracts added lines with positions
# ============================================================

def test_1_patch_parser():
    added = parse_added_lines(_SAMPLE_PATCH)
    contents = [line.content for line in added]
    numbers = [line.number for line in added]

    passed = (
        len(added) == 3
        and "secret = " in contents[0]
        and "verify = False" in contents[1]
        and numbers == [4, 5, 6]
    )
    details = "  Added lines: %d\n  Numbers: %s\n  Contents: %s" % (
        len(added), numbers, contents,
    )
    return _print(1, "Patch Parser", passed, details)


# ============================================================
# TEST 2: Scanner detects secrets and risky patterns
# ============================================================

def test_2_scanner_rules():
    added = parse_added_lines(_SAMPLE_PATCH)
    findings = scan_added_content("config.py", added)

    categories = {f.category for f in findings}
    passed = (
        "hardcoded_secret" in categories
        and "insecure_tls" in categories
        and "dangerous_eval" in categories
        and len(findings) >= 3
    )
    details = "  Categories found: %s" % sorted(categories)
    return _print(2, "Scanner Rules", passed, details)


# ============================================================
# TEST 3: Scanner maps severity to priority
# ============================================================

def test_3_scan_severity_priority():
    added = parse_added_lines(_SAMPLE_PATCH)
    findings = scan_added_content("config.py", added)

    secret = next(f for f in findings if f.category == "hardcoded_secret")
    passed = (
        secret.severity == "CRITICAL"
        and secret.priority == "P0"
        and secret.confidence >= 90
    )
    details = "  severity=%s priority=%s confidence=%.0f" % (
        secret.severity, secret.priority, secret.confidence,
    )
    return _print(3, "Severity/Priority Mapping", passed, details)


# ============================================================
# TEST 4: PR comment markdown built correctly
# ============================================================

def test_4_pr_comment():
    added = parse_added_lines(_SAMPLE_PATCH)
    findings = scan_added_content("config.py", added)

    body = build_pr_comment("octocat", "repo", 42, "Add config", findings)
    passed = (
        "PR Analysis" in body
        and "hardcoded_secret" not in body  # uses message text, not category
        and "github_pat" not in body  # raw secret value must not be echoed
        and "config.py" in body
        and "RepoLens" in body
    )
    details = body[:300] + ("\n  ... (%d chars)" % len(body))
    return _print(4, "PR Comment Markdown", passed, details)


# ============================================================
# TEST 5: Webhook signature verification
# ============================================================

def _signed_post(payload: dict, secret: str | None = None) -> dict:
    secret = secret or "test-webhook-secret"
    body = json.dumps(payload).encode("utf-8")
    signature = "sha256=" + hmac.new(
        secret.encode("utf-8"), body, hashlib.sha256
    ).hexdigest()
    return {
        "headers": {
            "X-GitHub-Event": payload.get("_event", "push"),
            "X-Hub-Signature-256": signature,
        },
        "content": body,
    }


def test_5_webhook_signature():
    payload = {
        "_event": "push",
        "ref": "refs/heads/main",
        "repository": {
            "clone_url": "https://github.com/octocat/Hello-World",
        },
    }
    req = _signed_post(payload)

    # Valid signature -> queued
    ok = client.post(
        "/api/v1/webhooks/github", headers=req["headers"], content=req["content"]
    )
    valid = ok.status_code == 200 and ok.json().get("status") == "queued"

    # Wrong secret -> 401
    bad = _signed_post(payload, secret="wrong-secret")
    rejected = client.post(
        "/api/v1/webhooks/github", headers=bad["headers"], content=bad["content"]
    )
    invalid = rejected.status_code == 401

    passed = valid and invalid
    details = "  Valid signature -> %d %s\n  Bad signature  -> %d %s" % (
        ok.status_code, ok.json().get("status"),
        rejected.status_code, rejected.json().get("detail"),
    )
    return _print(5, "Webhook Signature", passed, details)


# ============================================================
# TEST 6: Webhook events (ping, pull_request)
# ============================================================

def test_6_webhook_events():
    # ping -> pong
    ping_body = json.dumps({"zen": "keep it simple"}).encode()
    ping_sig = "sha256=" + hmac.new(
        b"test-webhook-secret", ping_body, hashlib.sha256
    ).hexdigest()
    ping = client.post(
        "/api/v1/webhooks/github",
        headers={"X-GitHub-Event": "ping", "X-Hub-Signature-256": ping_sig},
        content=ping_body,
    )
    ping_ok = ping.status_code == 200 and ping.json().get("status") == "pong"

    # pull_request opened -> queued (kind pull_request)
    pr_payload = {
        "_event": "pull_request",
        "action": "opened",
        "pull_request": {"number": 99},
        "repository": {"clone_url": "https://github.com/octocat/Hello-World"},
    }
    req = _signed_post(pr_payload)
    pr = client.post(
        "/api/v1/webhooks/github", headers=req["headers"], content=req["content"]
    )
    pr_ok = (
        pr.status_code == 200
        and pr.json().get("status") == "queued"
        and pr.json().get("kind") == "pull_request"
    )

    # pull_request closed -> ignored
    closed_payload = dict(pr_payload, action="closed")
    req = _signed_post(closed_payload)
    closed = client.post(
        "/api/v1/webhooks/github", headers=req["headers"], content=req["content"]
    )
    closed_ok = closed.json().get("status") == "ignored"

    passed = ping_ok and pr_ok and closed_ok
    details = (
        "  ping -> %s\n  opened -> %s\n  closed -> %s" % (
            "pong" if ping_ok else ping.json(),
            "queued" if pr_ok else pr.json(),
            "ignored" if closed_ok else closed.json(),
        )
    )
    return _print(6, "Webhook Events", passed, details)


# ============================================================
# TEST 7: analyze-pr validation + queueing
# ============================================================

def test_7_analyze_pr():
    # Invalid host -> 400
    bad_host = client.post("/api/v1/analyze-pr", json={
        "repository_url": "https://evil.com/owner/repo",
        "pull_number": 5,
    })
    host_ok = bad_host.status_code == 400

    # Malformed URL -> 422
    malformed = client.post("/api/v1/analyze-pr", json={
        "repository_url": "not-a-url",
        "pull_number": 5,
    })
    malformed_ok = malformed.status_code == 422

    # Invalid pull number -> 422
    bad_number = client.post("/api/v1/analyze-pr", json={
        "repository_url": "https://github.com/octocat/Hello-World",
        "pull_number": 0,
    })
    number_ok = bad_number.status_code == 422

    # Valid -> 202 with a PR job
    valid = client.post("/api/v1/analyze-pr", json={
        "repository_url": "https://github.com/octocat/Hello-World",
        "pull_number": 7,
    })
    body = valid.json()
    valid_ok = (
        valid.status_code == 202
        and body.get("job_type") == "PR"
        and body.get("pull_number") == 7
    )

    passed = host_ok and malformed_ok and number_ok and valid_ok
    details = (
        "  evil.com -> %d\n  not-a-url -> %d\n  PR #0 -> %d\n  valid -> %d %s" % (
            bad_host.status_code, malformed.status_code,
            bad_number.status_code, valid.status_code, body.get("job_type"),
        )
    )
    return _print(7, "Analyze Pull Request", passed, details)


# ============================================================
# TEST 8: GitHub connection status endpoint
# ============================================================

def test_8_github_status():
    response = client.get("/api/v1/github/status")
    body = response.json()
    passed = (
        response.status_code == 200
        and "authenticated" in body
        and body["webhook_secret_configured"] is True
        and "message" in body
    )
    details = "  status=%d authenticated=%s webhook=%s" % (
        response.status_code,
        body.get("authenticated"),
        body.get("webhook_secret_configured"),
    )
    return _print(8, "GitHub Status Endpoint", passed, details)


# ============================================================
# TEST 9: PR analysis history endpoints
# ============================================================

def test_9_pr_analysis_history():
    listing = client.get("/api/v1/pr-analyses")
    list_ok = listing.status_code == 200 and "pr_analyses" in listing.json()

    missing = client.get("/api/v1/pr-analyses/999999")
    missing_ok = missing.status_code == 404

    passed = list_ok and missing_ok
    details = "  list -> %d (total=%s)\n  missing id -> %d" % (
        listing.status_code, listing.json().get("total"),
        missing.status_code,
    )
    return _print(9, "PR Analysis History", passed, details)


# ============================================================
# TEST 10: PR jobs support PR metadata
# ============================================================

def test_10_pr_job_metadata():
    job = create_job(
        "https://github.com/octocat/Hello-World",
        job_type="PR",
        pull_number=77,
    )
    try:
        created_ok = (
            job.job_type == "PR"
            and job.pull_number == 77
            and job.status == "PENDING"
        )

        updated = update_job(
            job.job_id,
            status="COMPLETED",
            stage="COMPLETED",
            pr_analysis_id=123,
        )
        completed_ok = (
            updated.pr_analysis_id == 123
            and updated.status == "COMPLETED"
            and updated.completed_at is not None
        )

        fetched = get_job(job.job_id)
        fetch_ok = fetched.job_type == "PR" and fetched.pull_number == 77

        passed = created_ok and completed_ok and fetch_ok
        details = "  type=%s pr=#%s pr_analysis_id=%s" % (
            job.job_type, job.pull_number,
            updated.pr_analysis_id if updated else None,
        )
    finally:
        from app.core.database import SessionLocal
        from app.db_models.analysis_job import AnalysisJob
        db = SessionLocal()
        try:
            row = db.get(AnalysisJob, job.job_id)
            if row:
                db.delete(row)
                db.commit()
        finally:
            db.close()

    return _print(10, "PR Job Metadata", passed, details)


# ============================================================
# TEST 11: Quality gate evaluation
# ============================================================

def test_11_quality_gate():
    added = parse_added_lines(_SAMPLE_PATCH)
    dirty = scan_added_content("config.py", added)

    # Sample diff contains a critical secret -> FAIL
    gate_fail = evaluate_quality_gate(dirty)
    fail_ok = (
        gate_fail.result == "FAIL"
        and not gate_fail.passed
        and any("critical" in r for r in gate_fail.reasons)
        and gate_fail.counts["critical"] >= 1
        and gate_fail.counts["security"] >= 1
    )

    # Only low-severity, non-security findings -> PASS
    clean = [f for f in dirty if f.category == "debug_leftover"] or [
        ScanFinding(
            category="debug_leftover", severity="LOW",
            file_path="app.py", line_start=1,
            code_snippet="print('x')", message="debug",
            recommendation="remove", confidence=65,
        )
    ]
    gate_pass = evaluate_quality_gate(clean)
    pass_ok = gate_pass.result == "PASS" and gate_pass.passed

    # Health score below the minimum -> FAIL
    gate_health = evaluate_quality_gate([], health_score=45)
    health_ok = (
        gate_health.result == "FAIL"
        and any("Health" in r for r in gate_health.reasons)
    )

    # Clean + healthy -> PASS
    gate_all = evaluate_quality_gate([], health_score=95)
    all_ok = gate_all.result == "PASS"

    passed = fail_ok and pass_ok and health_ok and all_ok
    details = (
        "  dirty -> %s (reasons=%s)\n" % (gate_fail.result, gate_fail.reasons)
        + "  clean -> %s\n" % gate_pass.result
        + "  health 45 -> %s\n" % gate_health.result
        + "  clean+95 -> %s" % gate_all.result
    )
    return _print(11, "Quality Gate Evaluation", passed, details)


# ============================================================
# TEST 12: Commit status check posting
# ============================================================

def test_12_status_check_posting():
    class _Recorder:
        def __init__(self):
            self.token = "fake-token"
            self.calls = []

        def create_commit_status(self, owner, repo, sha, state, context,
                                 description, target_url):
            self.calls.append({
                "state": state, "sha": sha,
                "context": context, "description": description,
            })
            return {}

    original = settings.PR_POST_STATUS_CHECK
    try:
        settings.PR_POST_STATUS_CHECK = True

        recorder = _Recorder()
        gate_pass = evaluate_quality_gate([])
        ok_pass = _post_status_check(
            recorder, "octocat", "Hello-World",
            "a" * 40, "https://github.com/octocat/Hello-World/pull/1",
            gate_pass,
        )
        pass_state = recorder.calls[-1]["state"] if recorder.calls else None

        gate_fail = evaluate_quality_gate(scan_added_content("c.py", parse_added_lines(_SAMPLE_PATCH)))
        ok_fail = _post_status_check(
            recorder, "octocat", "Hello-World",
            "b" * 40, None, gate_fail,
        )
        fail_state = recorder.calls[-1]["state"] if recorder.calls else None

        # No token -> skipped
        recorder.token = None
        before = len(recorder.calls)
        ok_no_token = not _post_status_check(
            recorder, "octocat", "Hello-World", "c" * 40, None, gate_fail,
        )
        skipped = len(recorder.calls) == before

        # Disabled -> skipped
        settings.PR_POST_STATUS_CHECK = False
        recorder.token = "fake-token"
        before = len(recorder.calls)
        ok_disabled = not _post_status_check(
            recorder, "octocat", "Hello-World", "d" * 40, None, gate_pass,
        )
        skipped_disabled = len(recorder.calls) == before

        passed = (
            ok_pass and pass_state == "success"
            and ok_fail and fail_state == "failure"
            and ok_no_token and skipped
            and ok_disabled and skipped_disabled
            and len(recorder.calls) == 2
        )
        details = (
            "  PASS -> state=%s\n" % pass_state
            + "  FAIL -> state=%s\n" % fail_state
            + "  no token -> skipped=%s\n" % skipped
            + "  disabled -> skipped=%s\n" % skipped_disabled
            + "  total statuses posted: %d" % len(recorder.calls)
        )
    finally:
        settings.PR_POST_STATUS_CHECK = original

    return _print(12, "Commit Status Check Posting", passed, details)


# ============================================================
# TEST 13: Full PR analysis service run (fake GitHub client)
# ============================================================

class _FakeGitHubClient:
    """Records comment + status posts; returns canned PR data."""

    def __init__(self):
        self.token = "fake-token"
        self.posted_comments: list[str] = []
        self.posted_statuses: list[dict] = []

    def close(self):
        pass

    def get_pull_request(self, owner, repo, number):
        return {
            "title": "Add config loader",
            "html_url": f"https://github.com/{owner}/{repo}/pull/{number}",
            "base": {"sha": "a" * 40},
            "head": {"sha": "b" * 40},
        }

    def get_pull_request_files(self, owner, repo, number, max_files=None):
        return [{
            "status": "modified",
            "filename": "config.py",
            "patch": _SAMPLE_PATCH,
        }]

    def post_pull_request_comment(self, owner, repo, number, body):
        self.posted_comments.append(body)
        return {}

    def create_commit_status(self, owner, repo, sha, state, context,
                             description, target_url):
        self.posted_statuses.append({"state": state, "sha": sha})
        return {}


def test_13_full_pr_service_run():
    import app.services.pr_analysis_service as pr_service
    from app.core.database import SessionLocal
    from app.db_models.pr_analysis import PrAnalysis

    original_class = pr_service.GitHubClient
    original_comment = settings.PR_POST_COMMENT
    original_status = settings.PR_POST_STATUS_CHECK
    fake = _FakeGitHubClient()
    # run_pr_analysis calls GitHubClient() internally — return the shared
    # fake instance so its recorded calls are visible to the test.
    pr_service.GitHubClient = lambda: fake  # type: ignore[assignment]
    settings.PR_POST_COMMENT = True
    settings.PR_POST_STATUS_CHECK = True

    pr_analysis_id = None
    try:
        result = run_pr_analysis(
            "https://github.com/octocat/Hello-World",
            42,
            post_comment=True,
        )
        pr_analysis_id = result.get("pr_analysis_id")

        result_ok = (
            result.get("error") is None
            and result.get("findings_count", 0) >= 3
            and result.get("gate_result") == "FAIL"
            and result.get("status_check_posted") is True
        )
        comment_ok = len(fake.posted_comments) == 1 and "RepoLens" in fake.posted_comments[0]
        status_ok = (
            len(fake.posted_statuses) == 1
            and fake.posted_statuses[0]["state"] == "failure"
            and fake.posted_statuses[0]["sha"] == "b" * 40
        )

        # Persisted gate fields + API exposure
        db = SessionLocal()
        try:
            record = db.get(PrAnalysis, pr_analysis_id)
            persist_ok = (
                record is not None
                and record.gate_result == "FAIL"
                and record.gate_reasons
                and record.comment_posted is True
                and record.status_check_posted is True
            )
        finally:
            db.close()

        api = client.get(f"/api/v1/pr-analyses/{pr_analysis_id}")
        api_ok = (
            api.status_code == 200
            and api.json().get("gate_result") == "FAIL"
            and api.json().get("status_check_posted") is True
            and isinstance(api.json().get("gate_reasons"), list)
        )

        passed = result_ok and comment_ok and status_ok and persist_ok and api_ok
        details = (
            "  findings=%s gate=%s status_posted=%s\n" % (
                result.get("findings_count"), result.get("gate_result"),
                result.get("status_check_posted"),
            )
            + "  comments=%d statuses=%d\n" % (
                len(fake.posted_comments), len(fake.posted_statuses),
            )
            + "  api gate=%s reasons=%s" % (
                api.json().get("gate_result"), api.json().get("gate_reasons"),
            )
        )
    finally:
        pr_service.GitHubClient = original_class
        settings.PR_POST_COMMENT = original_comment
        settings.PR_POST_STATUS_CHECK = original_status

    return _print(13, "Full PR Service Run (Fake GitHub)", passed, details)


# ============================================================
# Run all tests
# ============================================================

def main():
    print()
    print("#" * 60)
    print("  PHASE 9 INTEGRATION TESTS")
    print("  Testing: PR scan, Webhooks, GitHub API")
    print("#" * 60)

    results = []
    tests = [
        ("Patch Parser", test_1_patch_parser),
        ("Scanner Rules", test_2_scanner_rules),
        ("Severity/Priority Mapping", test_3_scan_severity_priority),
        ("PR Comment Markdown", test_4_pr_comment),
        ("Webhook Signature", test_5_webhook_signature),
        ("Webhook Events", test_6_webhook_events),
        ("Analyze Pull Request", test_7_analyze_pr),
        ("GitHub Status Endpoint", test_8_github_status),
        ("PR Analysis History", test_9_pr_analysis_history),
        ("PR Job Metadata", test_10_pr_job_metadata),
        ("Quality Gate Evaluation", test_11_quality_gate),
        ("Commit Status Check Posting", test_12_status_check_posting),
        ("Full PR Service Run (Fake GitHub)", test_13_full_pr_service_run),
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