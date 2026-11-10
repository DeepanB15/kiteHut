"""
Phase 10 Integration Test Harness.

Tests: analysis settings (mode / enabled agents), finding status
lifecycle, custom quality gate config, trends, report generation
(markdown/json/pdf), and smart notifications.

Fully hermetic — no network or clones; reportlab is required (it is in
requirements.txt). Seeded database rows are created directly.

Run (harness):  cd backend && python -m tests.test_phase10_integration
Run (pytest):   cd backend && pytest tests/test_phase10_integration.py -q
"""

import atexit
import json
import os
import sys
import tempfile
from datetime import datetime, timezone

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

from fastapi.testclient import TestClient  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.core.database import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.db_models.repository import Repository  # noqa: E402
from app.db_models.analysis_run import AnalysisRun  # noqa: E402
from app.db_models.finding import Finding  # noqa: E402
from app.db_models.repository_health import RepositoryHealth  # noqa: E402
from app.db_models.pr_analysis import PrAnalysis  # noqa: E402
from app.db_models.pr_finding import PrFinding  # noqa: E402
from app.engines.quality_gate import evaluate_quality_gate  # noqa: E402

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


def _seed_repo_run_finding(
    *,
    repo_url="https://github.com/octocat/Hello-World",
    repo_name="Hello-World",
    priority="P0",
    category="security_risk",
    statement="A secret is hardcoded",
    fingerprint="security_risk:hardcoded_secret:config.py",
    health_score=None,
    health_level=None,
) -> tuple[int, int, int]:
    """Seed a repository + completed run + finding. Returns (repo_id, run_id, finding_id)."""
    db = SessionLocal()
    try:
        repo = db.query(Repository).filter(
            Repository.github_url == repo_url
        ).first()
        if not repo:
            repo = Repository(
                github_url=repo_url, owner="octocat", name=repo_name,
                first_analyzed_at=datetime.now(timezone.utc),
                last_analyzed_at=datetime.now(timezone.utc),
            )
            db.add(repo)
            db.flush()

        run = AnalysisRun(
            repository_id=repo.id, status="COMPLETED",
            mode="balanced", total_findings=1,
        )
        db.add(run)
        db.flush()

        finding = Finding(
            analysis_run_id=run.id, fingerprint=fingerprint,
            claim_type="hardcoded_secret", category=category,
            statement=statement, source_agent="security_agent",
            truth_value="TRUE", confidence=95.0,
            severity="CRITICAL", severity_score=10,
            user_impact=10, system_impact=10, business_impact=10,
            overall_impact=10, exploitability=10,
            final_score=95, priority=priority,
        )
        db.add(finding)
        db.flush()

        if health_score is not None:
            db.add(RepositoryHealth(
                analysis_run_id=run.id, repository_id=repo.id,
                overall_score=health_score,
                health_level=health_level or "GOOD",
                total_findings=1, critical_findings=1,
                summary="Seeded health",
            ))

        db.commit()
        return repo.id, run.id, finding.id
    finally:
        db.close()


# ============================================================
# TEST 1: Analysis settings validation
# ============================================================

def test_1_analysis_settings():
    # Valid fast mode + security agent -> 202
    ok = client.post("/api/v1/analyze", json={
        "repository_url": "https://github.com/octocat/Hello-World",
        "mode": "fast",
        "enabled_agents": ["security"],
    })
    valid = ok.status_code == 202

    # Invalid mode -> 422
    bad_mode = client.post("/api/v1/analyze", json={
        "repository_url": "https://github.com/octocat/Hello-World",
        "mode": "turbo",
    })
    mode_ok = bad_mode.status_code == 422

    # Unknown agent -> 422
    bad_agent = client.post("/api/v1/analyze", json={
        "repository_url": "https://github.com/octocat/Hello-World",
        "mode": "deep",
        "enabled_agents": ["hacker"],
    })
    agent_ok = bad_agent.status_code == 422

    # Deep mode with all agents -> 202
    deep = client.post("/api/v1/analyze", json={
        "repository_url": "https://github.com/octocat/Hello-World",
        "mode": "deep",
        "enabled_agents": ["architecture", "security", "quality", "testing"],
    })
    deep_ok = deep.status_code == 202

    passed = valid and mode_ok and agent_ok and deep_ok
    details = (
        "  fast+security -> %d\n  mode=turbo -> %d\n"
        "  agent=hacker -> %d\n  deep+all -> %d" % (
            ok.status_code, bad_mode.status_code,
            bad_agent.status_code, deep.status_code,
        )
    )
    return _print(1, "Analysis Settings Validation", passed, details)


# ============================================================
# TEST 2: Workflow router respects enabled agents
# ============================================================

def test_2_workflow_agent_routing():
    from app.graph.workflow import _fan_out_router

    state = {
        "mode": "fast",
        "enabled_agents": ["security"],
        "_arch_done": False, "_sec_done": False, "_qual_done": False,
        "_testing_done": False,
    }
    first = _fan_out_router(state)  # skips architecture/quality

    state["_sec_done"] = True
    second = _fan_out_router(state)  # security done, testing disabled -> verification

    state = {
        "mode": "balanced",
        "enabled_agents": [],
        "_arch_done": False, "_sec_done": False, "_qual_done": False,
        "_testing_done": False,
    }
    third = _fan_out_router(state)  # balanced -> architecture first

    passed = (
        first == "security"
        and second == "verification"
        and third == "architecture"
    )
    details = "  fast -> %s\n  fast done -> %s\n  balanced -> %s" % (
        first, second, third,
    )
    return _print(2, "Workflow Agent Routing", passed, details)


# ============================================================
# TEST 3: Finding status lifecycle
# ============================================================

def test_3_finding_status_lifecycle():
    _, run_id, finding_id = _seed_repo_run_finding(priority="P1")

    # Valid transition -> 200
    ok = client.patch(f"/api/v1/findings/{finding_id}/status", json={
        "status": "ACCEPTED_RISK", "note": "documented in README",
    })
    valid = ok.status_code == 200 and ok.json()["status"] == "ACCEPTED_RISK"

    # Invalid status -> 422
    bad = client.patch(f"/api/v1/findings/{finding_id}/status", json={
        "status": "MAYBE",
    })
    invalid = bad.status_code == 422

    # Missing finding -> 404
    missing = client.patch("/api/v1/findings/999999/status", json={
        "status": "OPEN",
    })
    not_found = missing.status_code == 404

    # Status filter in the findings list
    listing = client.get(f"/api/v1/analyses/{run_id}/findings?status=ACCEPTED_RISK")
    filtered = listing.status_code == 200 and listing.json()["total"] == 1

    passed = valid and invalid and not_found and filtered
    details = (
        "  patch -> %d %s\n  invalid -> %d\n  missing -> %d\n"
        "  filter total -> %s" % (
            ok.status_code, ok.json().get("status"),
            bad.status_code, missing.status_code,
            listing.json().get("total"),
        )
    )
    return _print(3, "Finding Status Lifecycle", passed, details)


# ============================================================
# TEST 4: PR finding status lifecycle
# ============================================================

def test_4_pr_finding_status_lifecycle():
    db = SessionLocal()
    try:
        repo = db.query(Repository).first()
        pr = PrAnalysis(
            repository_id=repo.id, pull_number=7,
            status="COMPLETED", findings_count=1,
        )
        db.add(pr)
        db.flush()
        pf = PrFinding(
            pr_analysis_id=pr.id, category="hardcoded_secret",
            severity="CRITICAL", priority="P0",
            file_path="config.py", message="secret",
            source="rule", confidence=95,
        )
        db.add(pf)
        db.commit()
        pr_id, pf_id = pr.id, pf.id
    finally:
        db.close()

    ok = client.patch(f"/api/v1/pr-findings/{pf_id}/status", json={
        "status": "FALSE_POSITIVE",
    })
    valid = ok.status_code == 200 and ok.json()["status"] == "FALSE_POSITIVE"

    # Detail endpoint reflects the status
    detail = client.get(f"/api/v1/pr-analyses/{pr_id}")
    reflected = (
        detail.status_code == 200
        and detail.json()["findings"][0]["status"] == "FALSE_POSITIVE"
    )

    passed = valid and reflected
    details = "  patch -> %d %s\n  detail reflected -> %s" % (
        ok.status_code, ok.json().get("status"), reflected,
    )
    return _print(4, "PR Finding Status Lifecycle", passed, details)


# ============================================================
# TEST 5: Custom quality gate config
# ============================================================

def test_5_quality_gate_config():
    repo_id, _, _ = _seed_repo_run_finding()

    # Missing repo -> 404
    missing = client.get("/api/v1/repositories/999999/quality-gate")
    not_found = missing.status_code == 404

    # Defaults view
    defaults = client.get(f"/api/v1/repositories/{repo_id}/quality-gate")
    uses_defaults = (
        defaults.status_code == 200
        and defaults.json().get("uses_defaults") is True
    )

    # Update
    saved = client.put(f"/api/v1/repositories/{repo_id}/quality-gate", json={
        "critical_limit": 2, "security_limit": 1, "min_health": 55,
    })
    updated = (
        saved.status_code == 200
        and saved.json()["critical_limit"] == 2
        and saved.json()["uses_defaults"] is False
    )

    # Gate evaluation honors the overrides
    class FakeFinding:
        def __init__(self, category, severity):
            self.category = category
            self.severity = severity

    gate = evaluate_quality_gate(
        [FakeFinding("hardcoded_secret", "CRITICAL")],
        limits={"critical_limit": 2, "security_limit": 1, "min_health": 55},
    )
    passed_override = gate.result == "PASS"  # 1 critical <= 2, 1 security <= 1

    strict = evaluate_quality_gate(
        [FakeFinding("hardcoded_secret", "CRITICAL")],
        limits={"critical_limit": 0, "security_limit": 0, "min_health": 60},
    )
    failed_strict = strict.result == "FAIL"

    passed = not_found and uses_defaults and updated and passed_override and failed_strict
    details = (
        "  missing -> %d\n  defaults -> %s\n  update -> %d\n"
        "  override PASS -> %s\n  strict FAIL -> %s" % (
            missing.status_code, uses_defaults, saved.status_code,
            passed_override, failed_strict,
        )
    )
    return _print(5, "Custom Quality Gate Config", passed, details)


# ============================================================
# TEST 6: Trends endpoint
# ============================================================

def test_6_trends():
    repo_id, run_id, _ = _seed_repo_run_finding(
        repo_url="https://github.com/octocat/TrendRepo",
        repo_name="TrendRepo",
        health_score=72, health_level="GOOD",
    )

    response = client.get(f"/api/v1/repositories/{repo_id}/trends")
    body = response.json()
    point = body["trend"][0] if body["trend"] else {}

    passed = (
        response.status_code == 200
        and len(body["trend"]) == 1
        and point.get("health_score") == 72
        and point.get("p0") == 1
        and point.get("security") == 1  # security_risk normalized to security
        and point.get("analysis_run_id") == run_id
    )
    details = "  trend points: %d\n  point: %s" % (
        len(body["trend"]),
        {k: point.get(k) for k in
         ("analysis_run_id", "health_score", "p0", "security")},
    )
    return _print(6, "Repository Trends", passed, details)


# ============================================================
# TEST 7: Reports (markdown / json / pdf)
# ============================================================

def test_7_reports():
    repo_id, run_id, finding_id = _seed_repo_run_finding(
        health_score=72, health_level="GOOD",
    )

    md = client.get(f"/api/v1/analyses/{run_id}/report.md")
    md_ok = (
        md.status_code == 200
        and "Hello-World" in md.text
        and "Findings" in md.text
        and "P0" in md.text
    )

    js = client.get(f"/api/v1/analyses/{run_id}/report.json")
    json_ok = js.status_code == 200
    if json_ok:
        data = json.loads(js.text)
        json_ok = (
            data["repository"]["name"] == "Hello-World"
            and data["analysis"]["id"] == run_id
            and len(data["findings"]) == 1
        )

    pdf = client.get(f"/api/v1/analyses/{run_id}/report.pdf")
    pdf_ok = (
        pdf.status_code == 200
        and pdf.headers.get("content-type") == "application/pdf"
        and pdf.content.startswith(b"%PDF")
    )

    passed = md_ok and json_ok and pdf_ok
    details = (
        "  md -> %d (%d bytes)\n  json -> %d (%d bytes)\n"
        "  pdf -> %d (%d bytes, header=%s)" % (
            md.status_code, len(md.content),
            js.status_code, len(js.content),
            pdf.status_code, len(pdf.content),
            pdf.content[:5],
        )
    )
    return _print(7, "Report Generation (MD/JSON/PDF)", passed, details)


# ============================================================
# TEST 8: Notifications — generation, list, read
# ============================================================

def test_8_notifications():
    from app.services.notifications_service import generate_after_analysis

    # Run 1: one P0 security finding, health 80
    repo1, run1, f1 = _seed_repo_run_finding(
        repo_url="https://github.com/octocat/RepoOne",
        repo_name="RepoOne",
        health_score=80, health_level="GOOD",
    )
    n1 = generate_after_analysis(
        repository_id=repo1, analysis_run_id=run1, repository_name="RepoOne",
    )
    kinds1 = {n.kind for n in n1}
    new_p0 = "NEW_P0" in kinds1
    security_risk = "SECURITY_RISK" in kinds1

    # Run 2: same fingerprint gone (resolved), health drops to 70
    db = SessionLocal()
    try:
        repo = db.get(Repository, repo1)
        run2 = AnalysisRun(repository_id=repo1, status="COMPLETED",
                           mode="balanced", total_findings=0)
        db.add(run2)
        db.flush()
        db.add(RepositoryHealth(
            analysis_run_id=run2.id, repository_id=repo1,
            overall_score=70, health_level="FAIR",
            total_findings=0, critical_findings=0, summary="Improved",
        ))
        db.commit()
        run2_id = run2.id
    finally:
        db.close()

    n2 = generate_after_analysis(
        repository_id=repo1, analysis_run_id=run2_id, repository_name="RepoOne",
    )
    kinds2 = {n.kind for n in n2}
    resolved = "CRITICAL_RESOLVED" in kinds2
    health_drop = "HEALTH_DROP" in kinds2

    # List + unread count + mark read
    listing = client.get("/api/v1/notifications")
    total = listing.json()["total"]
    unread = listing.json()["unread"]
    listed = listing.status_code == 200 and total == len(n1) + len(n2)

    first_id = listing.json()["notifications"][0]["id"]
    read = client.post(f"/api/v1/notifications/{first_id}/read")
    read_ok = read.status_code == 200 and read.json()["read"] is True

    unread_after = client.get("/api/v1/notifications?unread_only=true")
    unread_ok = unread_after.json()["unread"] == unread - 1

    read_all = client.post("/api/v1/notifications/read-all")
    read_all_ok = read_all.status_code == 200 and read_all.json()["updated"] >= 1

    passed = (
        new_p0 and security_risk and resolved and health_drop
        and listed and read_ok and unread_ok and read_all_ok
    )
    details = (
        "  run1 kinds: %s\n  run2 kinds: %s\n  total=%d unread=%d\n"
        "  read -> %s, unread-only -> %d, read-all -> %d" % (
            sorted(kinds1), sorted(kinds2), total, unread,
            read_ok, unread_after.json()["unread"], read_all.json()["updated"],
        )
    )
    return _print(8, "Smart Notifications", passed, details)


# ============================================================
# TEST 9: Notification webhook delivery
# ============================================================

def test_9_notification_webhook():
    from unittest import mock

    from app.services import notifications_service
    from app.services.notifications_service import generate_after_analysis

    repo_id, run_id, _ = _seed_repo_run_finding(
        repo_url="https://github.com/octocat/WebhookRepo",
        repo_name="WebhookRepo",
    )

    original_url = settings.NOTIFICATION_WEBHOOK_URL
    try:
        settings.NOTIFICATION_WEBHOOK_URL = "https://hooks.example.com/xyz"
        with mock.patch.object(
            notifications_service.httpx, "post"
        ) as fake_post:
            fake_post.return_value.status_code = 200
            fake_post.return_value.raise_for_status.return_value = None

            generate_after_analysis(
                repository_id=repo_id,
                analysis_run_id=run_id,
                repository_name="WebhookRepo",
            )

            calls = fake_post.call_args_list
            delivered = (
                len(calls) >= 1
                and calls[0].kwargs["json"]["kind"] in
                ("NEW_P0", "SECURITY_RISK")
                and calls[0].kwargs["json"]["repository"] == "WebhookRepo"
            )
            details = "  webhook calls: %d, payload kind: %s" % (
                len(calls),
                calls[0].kwargs["json"]["kind"] if calls else "none",
            )
    finally:
        settings.NOTIFICATION_WEBHOOK_URL = original_url

    return _print(9, "Notification Webhook Delivery", delivered, details)


# ============================================================
# Run all tests
# ============================================================

def main():
    print()
    print("#" * 60)
    print("  PHASE 10 INTEGRATION TESTS")
    print("  Testing: settings, statuses, gate, trends, reports, notifications")
    print("#" * 60)

    results = []
    tests = [
        ("Analysis Settings Validation", test_1_analysis_settings),
        ("Workflow Agent Routing", test_2_workflow_agent_routing),
        ("Finding Status Lifecycle", test_3_finding_status_lifecycle),
        ("PR Finding Status Lifecycle", test_4_pr_finding_status_lifecycle),
        ("Custom Quality Gate Config", test_5_quality_gate_config),
        ("Repository Trends", test_6_trends),
        ("Report Generation (MD/JSON/PDF)", test_7_reports),
        ("Smart Notifications", test_8_notifications),
        ("Notification Webhook Delivery", test_9_notification_webhook),
    ]

    for name, fn in tests:
        try:
            results.append((name, fn()))
        except Exception as e:  # noqa: BLE001
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