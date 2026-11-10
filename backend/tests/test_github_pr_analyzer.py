"""
Unit and Integration Tests for Pull Request Analyzer and Commenter (Layer 11).
"""

from pathlib import Path
from app.github.commenter import PRCommentFormatter
from app.github.models.github_models import (
    PRFileChange,
    PullRequestInfo,
    QualityGateResult,
    QualityGateRule,
)
from app.github.pr_analyzer import PullRequestAnalyzer
from app.intelligence.models.findings import Finding, FindingCategory, FindingSeverity


def test_pr_comment_formatter_markdown_output():
    """Verify PR comment formatter creates valid GitHub-flavored markdown."""
    gate_res = QualityGateResult(
        passed=False,
        p0_count=1,
        reasons=["Found 1 Critical (P0) finding(s)."],
        summary="RepoLens Quality Gate: FAILED",
    )

    finding = Finding(
        category=FindingCategory.SECURITY,
        severity=FindingSeverity.CRITICAL,
        confidence=95.0,
        priority="P0",
        title="Hardcoded API Secret in auth.py",
        description="Plaintext Stripe token found in source.",
        file_path="src/auth.py",
        line_number=12,
        code_snippet="api_key = 'sk_live_12345'",
        recommendation="Use os.getenv('STRIPE_API_KEY')",
    )

    md = PRCommentFormatter.format_review_markdown(
        pr_number=42,
        findings=[finding],
        gate_result=gate_res,
    )

    assert "## 🔍 RepoLens PR Analysis — PR #42" in md
    assert "❌ **FAILED**" in md
    assert "[P0] Hardcoded API Secret in auth.py" in md
    assert "`src/auth.py`:12" in md
    assert "sk_live_12345" in md
    assert "💡 **Suggested Remediation**" in md


def test_pull_request_analyzer_end_to_end(temp_workspace):
    """Verify PullRequestAnalyzer scans changed files, triggers verification, and produces report."""
    ws = temp_workspace
    vuln_file = ws / "src" / "vuln_service.py"
    vuln_file.write_text("api_token = 'sk_live_998877665544'\n", encoding="utf-8")

    analyzer = PullRequestAnalyzer(str(ws))

    pr_info = PullRequestInfo(
        number=101,
        title="Add payment integration",
        head_sha="abc1234",
        base_sha="def5678",
        author="alice",
    )

    file_changes = [
        PRFileChange(
            file_path="src/vuln_service.py",
            status="added",
            additions=1,
            deletions=0,
            patch="@@ -0,0 +1 @@\n+api_token = 'sk_live_998877665544'",
        )
    ]

    report = analyzer.analyze_pull_request(
        pr_info=pr_info,
        changed_files=file_changes,
        gate_rules=QualityGateRule(max_p0=0, max_security_findings=0),
    )

    assert report.pr_number == 101
    assert report.head_sha == "abc1234"
    assert len(report.findings) >= 1
    assert report.quality_gate.passed is False
    assert "src/vuln_service.py" in report.summary_markdown
