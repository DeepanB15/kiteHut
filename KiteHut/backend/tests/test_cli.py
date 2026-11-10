"""
Tests for RepoLens CLI commands and user interface.
Validates all subcommands, arguments, options, formatting, and error handling.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from click.testing import CliRunner

from app.cli.main import cli
from app.cli.ui import (
    SYM_CHECK,
    SYM_CROSS,
    SYM_WARN,
    format_health_score,
    priority_badge,
    truth_status_badge,
)
from app.intelligence.models.findings import (
    Finding,
    FindingCategory,
    FindingSeverity,
)
from app.verification.models.truth import TruthStatus


@pytest.fixture
def runner():
    """Click CLI test runner."""
    return CliRunner()


class TestCliUI:
    """Tests for CLI UI helpers and badges."""

    def test_format_health_score(self):
        good = format_health_score(95.0)
        assert "95.0" in good

        warn = format_health_score(75.0)
        assert "75.0" in warn

        bad = format_health_score(45.0)
        assert "45.0" in bad

    def test_badges(self):
        p0 = priority_badge("P0")
        assert "P0" in p0

        p3 = priority_badge("P3")
        assert "P3" in p3

        ts_true = truth_status_badge(TruthStatus.TRUE)
        assert "VERIFIED" in ts_true


class TestCliCommands:
    """Tests for Click command groups and individual subcommands."""

    def test_cli_help(self, runner):
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "RepoLens" in result.output
        assert "Local AI Engineering Agent" in result.output
        assert "init" in result.output
        assert "status" in result.output
        assert "review" in result.output
        assert "findings" in result.output
        assert "fix" in result.output
        assert "ask" in result.output
        assert "report" in result.output
        assert "git" in result.output
        assert "github" in result.output
        assert "doctor" in result.output
        assert "models" in result.output
        assert "start" in result.output

    def test_init_command(self, runner, temp_workspace):
        # 1. Initialize repo
        res = runner.invoke(cli, ["init", "--path", str(temp_workspace)])
        assert res.exit_code == 0
        assert "Initializing RepoLens" in res.output
        assert "RepoLens initialized successfully" in res.output

        config_path = temp_workspace / ".repolens.json"
        assert config_path.exists()
        config_data = json.loads(config_path.read_text(encoding="utf-8"))
        assert config_data["version"] == "2.0"
        assert config_data["repository_name"] == temp_workspace.name

        # 2. Re-init without force should warn
        res2 = runner.invoke(cli, ["init", "--path", str(temp_workspace)])
        assert res2.exit_code == 0
        assert "already initialized" in res2.output

        # 3. Re-init with force should succeed
        res3 = runner.invoke(cli, ["init", "--path", str(temp_workspace), "--force"])
        assert res3.exit_code == 0
        assert "RepoLens initialized successfully" in res3.output

    def test_status_command(self, runner, temp_git_repo):
        res = runner.invoke(cli, ["status", "--path", str(temp_git_repo)])
        assert res.exit_code == 0
        assert "RepoLens Status" in res.output
        assert "Repository Context:" in res.output
        assert "Git Version Control:" in res.output

    def test_doctor_command(self, runner, temp_git_repo):
        res = runner.invoke(cli, ["doctor", "--path", str(temp_git_repo)])
        assert res.exit_code == 0
        assert "RepoLens Diagnostics (Doctor)" in res.output
        assert "Python Runtime:" in res.output
        assert "Workspace Access:" in res.output
        assert "Git Repository:" in res.output
        assert "Core Dependencies:" in res.output

    def test_models_command(self, runner):
        res = runner.invoke(cli, ["models"])
        assert res.exit_code == 0
        assert "Local AI Inference Engine" in res.output

    def test_findings_command_list_and_filter(self, runner, temp_git_repo):
        # Scan findings in temp git repo
        res = runner.invoke(cli, ["findings", "--path", str(temp_git_repo)])
        assert res.exit_code == 0
        assert "Verified Findings" in res.output

        # Filter by priority
        res_p = runner.invoke(cli, ["findings", "--path", str(temp_git_repo), "--priority", "P0"])
        assert res_p.exit_code == 0

        # Filter by category
        res_c = runner.invoke(cli, ["findings", "--path", str(temp_git_repo), "--category", "security"])
        assert res_c.exit_code == 0

    def test_findings_command_inspect(self, runner, temp_git_repo):
        # Inspect missing finding
        res = runner.invoke(cli, ["findings", "--path", str(temp_git_repo), "--inspect", "non-existent-id"])
        assert res.exit_code == 0
        assert "Finding ID 'non-existent-id' not found" in res.output

    def test_review_command(self, runner, temp_git_repo):
        # Full review
        res = runner.invoke(cli, ["review", "--path", str(temp_git_repo)])
        assert res.exit_code == 0
        assert "RepoLens Intelligence Review" in res.output
        assert "Health Score:" in res.output
        assert "Quality Gate:" in res.output

        # Diff review
        res_diff = runner.invoke(cli, ["review", "--path", str(temp_git_repo), "--diff-only"])
        assert res_diff.exit_code == 0
        assert "Incremental Git Diff" in res_diff.output

    def test_report_command_markdown(self, runner, temp_git_repo):
        res = runner.invoke(cli, ["report", "--path", str(temp_git_repo)])
        assert res.exit_code == 0
        assert "# RepoLens Audit Report" in res.output
        assert "## 1. Project Overview" in res.output
        assert "## 2. Quality Gate Status" in res.output

    def test_report_command_json(self, runner, temp_git_repo):
        res = runner.invoke(cli, ["report", "--path", str(temp_git_repo), "--format", "json"])
        assert res.exit_code == 0
        # Parse output as JSON (skipping initial log message)
        json_start = res.output.find("{")
        assert json_start != -1
        json_str = res.output[json_start:]
        data = json.loads(json_str)
        assert "repository" in data
        assert "health_score" in data
        assert "quality_gate" in data
        assert "findings" in data

    def test_report_command_save_file(self, runner, temp_git_repo):
        out_file = temp_git_repo / "audit_report.md"
        res = runner.invoke(cli, ["report", "--path", str(temp_git_repo), "--output", str(out_file)])
        assert res.exit_code == 0
        assert out_file.exists()
        content = out_file.read_text(encoding="utf-8")
        assert "# RepoLens Audit Report" in content

    def test_git_subcommands(self, runner, temp_git_repo):
        # Git status
        res_status = runner.invoke(cli, ["git", "status", "--path", str(temp_git_repo)])
        assert res_status.exit_code == 0
        assert "Git Status" in res_status.output
        assert "Clean" in res_status.output

        # Git diff
        res_diff = runner.invoke(cli, ["git", "diff", "--path", str(temp_git_repo)])
        assert res_diff.exit_code == 0
        assert "Git Diff" in res_diff.output

        # Git commit with no changes
        res_commit_empty = runner.invoke(cli, ["git", "commit", "--path", str(temp_git_repo)])
        assert res_commit_empty.exit_code == 0
        assert "No changes detected" in res_commit_empty.output

        # Modify file and commit
        src_file = temp_git_repo / "src" / "main.py"
        src_file.write_text("def new_func(): pass\n", encoding="utf-8")

        res_commit = runner.invoke(
            cli,
            ["git", "commit", "--path", str(temp_git_repo), "-a", "-m", "feat: add new_func"],
            input="y\n",
        )
        assert res_commit.exit_code == 0
        assert "Created commit" in res_commit.output

    def test_github_subcommands(self, runner, temp_git_repo):
        # Quality Gate check
        res_check = runner.invoke(cli, ["github", "check", "--path", str(temp_git_repo)])
        assert res_check.exit_code == 0
        assert "GitHub Quality Gate Check" in res_check.output

        # PR simulation
        res_pr = runner.invoke(cli, ["github", "pr", "101", "--path", str(temp_git_repo)])
        assert res_pr.exit_code == 0
        assert "Simulating PR #101 Analysis" in res_pr.output

    def test_fix_command_missing_finding(self, runner, temp_git_repo):
        res = runner.invoke(cli, ["fix", "nonexistent-finding-999", "--path", str(temp_git_repo)])
        assert res.exit_code == 0
        assert "Finding ID 'nonexistent-finding-999' not found" in res.output

    def test_ask_command(self, runner, temp_git_repo):
        # Execute ask command with mocked AgentCore to avoid calling live LLM in unit test
        with patch("app.cli.commands.ask_cmd.AgentCore") as MockAgentCore:
            mock_core_instance = MagicMock()
            MockAgentCore.return_value = mock_core_instance

            mock_task_state = MagicMock()
            mock_task_state.task_id = "test-task-123"
            mock_core_instance.create_task.return_value = mock_task_state

            mock_final_state = MagicMock()
            from app.agent.state.agent_state import TaskStatus
            mock_final_state.status = TaskStatus.COMPLETED
            mock_final_state.final_answer = "The repository structure is well organized."
            mock_final_state.error = None
            mock_core_instance.run_task.return_value = mock_final_state

            res = runner.invoke(
                cli,
                ["ask", "Explain the main function", "--path", str(temp_git_repo), "-y"],
            )
            assert res.exit_code == 0
            assert "RepoLens Agent" in res.output
            assert "The repository structure is well organized." in res.output
            assert "Task executed successfully" in res.output
