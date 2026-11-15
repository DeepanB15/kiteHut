"""
Regression tests for remediation permission grant scoping and lifecycle,
plus the CLI interactive approval path.
"""

from unittest.mock import MagicMock

import click
from click.testing import CliRunner
import pytest

from app.action.loop.remediation_loop import ActionRemediationLoop
from app.action.models.patch import FileChangeType, FilePatch, ProposedPatch
from app.agent.permissions.manager import PermissionManager
from app.agent.permissions.policies import (
    DecisionType,
    PermissionRequest,
    PermissionType,
    RiskLevel,
)
from app.cli.commands.fix_cmd import _approval_decision
from app.intelligence.models.findings import Finding, FindingCategory, FindingSeverity


def permission_request(
    task_id: str = "task_1",
    repository_path: str = "/repo/alpha",
    tool_name: str = "apply_patch",
) -> PermissionRequest:
    return PermissionRequest(
        request_id=f"req_{task_id}",
        task_id=task_id,
        permission_type=PermissionType.WRITE,
        risk_level=RiskLevel.APPROVAL_REQUIRED,
        tool_name=tool_name,
        description="Write file",
        repository_path=repository_path,
    )


def test_task_grant_does_not_cross_repositories():
    """A task grant for one repository must not authorize another repository."""
    calls = []

    def callback(request):
        calls.append(request.repository_path)
        return (
            DecisionType.ALLOW_FOR_TASK if len(calls) == 1 else DecisionType.DENY
        )

    manager = PermissionManager(approval_callback=callback)

    assert manager.check_permission(permission_request(repository_path="/repo/alpha")) is True
    assert manager.check_permission(permission_request(repository_path="/repo/beta")) is False
    assert calls == ["/repo/alpha", "/repo/beta"]


def test_grant_permission_requires_repository_for_task_scope():
    manager = PermissionManager()

    with pytest.raises(ValueError):
        manager.grant_permission(
            "apply_patch", DecisionType.ALLOW_FOR_TASK, task_id="task_1"
        )


def test_revoke_task_grant_scoped_by_repository():
    manager = PermissionManager()
    manager.grant_permission(
        "apply_patch",
        DecisionType.ALLOW_FOR_TASK,
        task_id="task_1",
        repository_path="/repo/alpha",
    )
    manager.grant_permission(
        "apply_patch",
        DecisionType.ALLOW_FOR_TASK,
        task_id="task_1",
        repository_path="/repo/beta",
    )

    assert manager.check_permission(permission_request(repository_path="/repo/alpha")) is True

    manager.revoke_task_grants("task_1", "/repo/alpha")

    assert manager.check_permission(permission_request(repository_path="/repo/alpha")) is False
    assert manager.check_permission(permission_request(repository_path="/repo/beta")) is True

    manager.revoke_task_grants("task_1")

    assert manager.check_permission(permission_request(repository_path="/repo/beta")) is False


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "repo"
    (root / "src").mkdir(parents=True)
    (root / "src" / "app.py").write_text("value = 1\n", encoding="utf-8")
    return root


def make_finding() -> Finding:
    return Finding(
        category=FindingCategory.CONFIGURATION,
        severity=FindingSeverity.LOW,
        confidence=80.0,
        title="Remediation grant lifecycle",
        description="Test finding.",
        file_path="src/app.py",
    )


def make_patch(*file_patches: FilePatch) -> ProposedPatch:
    return ProposedPatch(
        finding_id="find_grant_lifecycle",
        title="Grant lifecycle patch",
        description="Patch used by grant lifecycle tests.",
        file_patches=list(file_patches),
    )


def test_grants_revoked_after_success(repo, monkeypatch):
    manager = PermissionManager(auto_allow_safe=True)
    loop = ActionRemediationLoop(str(repo), permission_manager=manager)
    patch = make_patch(
        FilePatch(
            file_path="src/app.py",
            change_type=FileChangeType.MODIFY,
            new_content="value = 2\n",
        )
    )
    monkeypatch.setattr(loop.planner, "plan_fix", lambda finding: patch)

    result = loop.remediate_finding(make_finding(), auto_approve=True, run_tests=False)

    assert result.success is True
    assert manager._task_grants == {}


def test_grants_revoked_after_denial(repo):
    manager = PermissionManager(auto_allow_safe=True)
    manager.check_permission = MagicMock(return_value=False)
    loop = ActionRemediationLoop(str(repo), permission_manager=manager)
    patch = make_patch(
        FilePatch(
            file_path="src/app.py",
            change_type=FileChangeType.MODIFY,
            new_content="value = 2\n",
        )
    )
    loop.planner.plan_fix = lambda finding: patch

    result = loop.remediate_finding(make_finding(), auto_approve=True, run_tests=False)

    assert result.success is False
    assert result.error == "Permission denied"
    assert manager._task_grants == {}


def test_grants_revoked_after_apply_failure(repo, monkeypatch):
    manager = PermissionManager(auto_allow_safe=True)
    loop = ActionRemediationLoop(str(repo), permission_manager=manager)
    # "src" is an existing directory, so writing it fails mid-patch.
    patch = make_patch(
        FilePatch(
            file_path="src",
            change_type=FileChangeType.CREATE,
            new_content="not a file\n",
        )
    )
    monkeypatch.setattr(loop.planner, "plan_fix", lambda finding: patch)

    result = loop.remediate_finding(make_finding(), auto_approve=True, run_tests=False)

    assert result.success is False
    assert result.rolled_back is True
    assert manager._task_grants == {}


def test_grants_revoked_after_test_failure(repo, monkeypatch):
    from app.action.models.patch import TestExecutionResult

    manager = PermissionManager(auto_allow_safe=True)
    loop = ActionRemediationLoop(str(repo), permission_manager=manager)
    patch = make_patch(
        FilePatch(
            file_path="src/app.py",
            change_type=FileChangeType.MODIFY,
            new_content="value = 2\n",
        )
    )
    monkeypatch.setattr(loop.planner, "plan_fix", lambda finding: patch)
    loop.test_runner.run_tests = MagicMock(
        return_value=TestExecutionResult(passed=False, error_message="failed")
    )

    result = loop.remediate_finding(make_finding(), auto_approve=True, run_tests=True)

    assert result.success is False
    assert result.rolled_back is True
    assert manager._task_grants == {}


def test_cli_interactive_approval_allows():
    """Existing CLI interactive approval still works."""

    @click.command()
    def command():
        click.echo(_approval_decision(permission_request(), False).value)

    result = CliRunner().invoke(command, input="y\n")

    assert result.exit_code == 0
    assert DecisionType.ALLOW_ONCE.value in result.output


def test_cli_interactive_approval_denies():
    @click.command()
    def command():
        click.echo(_approval_decision(permission_request(), False).value)

    result = CliRunner().invoke(command, input="n\n")

    assert result.exit_code == 0
    assert DecisionType.DENY.value in result.output


def test_cli_yes_flag_approves():
    decision = _approval_decision(permission_request(), True)

    assert decision == DecisionType.ALLOW_ONCE
