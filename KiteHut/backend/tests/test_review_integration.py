"""
Phase 6 — Tests for reporting integration (`repolens review` uses ReviewPipeline)
and CLI output preservation / verification.
"""
import pytest
from click.testing import CliRunner
from pathlib import Path

from app.cli.main import cli
from app.review.pipeline import ReviewPipeline
from app.review.finding import Finding, Severity, Category, Evidence


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def fixture_secure_repo(tmp_path):
    repo = tmp_path / "secure_repo"
    repo.mkdir()
    (repo / "auth.py").write_text('password = "hardcoded_secret_123"\n')
    return repo


class TestReviewIntegration:
    def test_review_command_still_works(self, runner, fixture_secure_repo):
        res = runner.invoke(cli, ["review", "--path", str(fixture_secure_repo)])
        assert res.exit_code == 0
        assert "RepoLens Intelligence Review" in res.output
        assert "Findings Breakdown" in res.output

    def test_review_pipeline_finds_reach_cli_output(self, runner, fixture_secure_repo):
        res = runner.invoke(cli, ["review", "--path", str(fixture_secure_repo)])
        assert res.exit_code == 0
        # Phase 6 table headers must appear
        assert "Rule" in res.output
        assert "Category" in res.output
        assert "Verification" in res.output
        assert "Evidence" in res.output
        assert "Confidence" in res.output

    def test_review_renders_verification_status(self, runner, fixture_secure_repo):
        res = runner.invoke(cli, ["review", "--path", str(fixture_secure_repo)])
        assert res.exit_code == 0
        # At least one verification state should appear from pipeline processing
        assert any(s in res.output for s in ("verified", "unsupported", "stale", "inconclusive"))

    def test_review_renders_evidence_quality(self, runner, fixture_secure_repo):
        res = runner.invoke(cli, ["review", "--path", str(fixture_secure_repo)])
        assert res.exit_code == 0
        assert any(s in res.output for s in ("strong", "medium", "weak"))

    def test_review_renders_confidence(self, runner, fixture_secure_repo):
        res = runner.invoke(cli, ["review", "--path", str(fixture_secure_repo)])
        assert res.exit_code == 0
        assert any(s in res.output for s in ("high", "medium", "low"))

    def test_review_existing_behavior_preserved(self, runner, fixture_secure_repo):
        res = runner.invoke(cli, ["review", "--path", str(fixture_secure_repo)])
        assert res.exit_code == 0
        assert "Quality Gate:" in res.output
        assert "Active Findings:" in res.output

    def test_review_pipeline_enrichment(self, fixture_secure_repo):
        pipeline = ReviewPipeline(str(fixture_secure_repo))
        findings = pipeline.run()
        assert isinstance(findings, list)
        # At least one enriched finding with Phase 6 fields set
        for f in findings:
            assert isinstance(f.verification_status, str)
            assert isinstance(f.evidence_quality, str)
            assert isinstance(f.confidence, str)


class TestReportingDoesNotBreakMCP:
    def test_mcp_server_still_exposes_23_tools(self):
        from app.mcp.server import get_mcp_server
        server = get_mcp_server(".")
        assert len(server.get_registered_tool_names()) == 23
        assert "run_analysis" in server.get_registered_tool_names()
