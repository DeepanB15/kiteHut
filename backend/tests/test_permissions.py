"""
Unit tests for the RepoLens Permission Management System.
"""

from app.agent.permissions.manager import PermissionManager
from app.agent.permissions.policies import (
    DecisionType,
    PermissionRequest,
    PermissionType,
    RiskLevel,
)


def test_safe_permission_auto_allowed():
    """Verify that SAFE operations are auto-allowed without triggering approval callback."""
    called = []

    def dummy_callback(req):
        called.append(req)
        return DecisionType.DENY

    pm = PermissionManager(approval_callback=dummy_callback, auto_allow_safe=True)

    safe_req = PermissionRequest(
        request_id="req_1",
        task_id="task_1",
        permission_type=PermissionType.READ,
        risk_level=RiskLevel.SAFE,
        tool_name="read_file",
        description="Read file",
        arguments={"path": "main.py"},
        repository_path="/test/repo",
    )

    allowed = pm.check_permission(safe_req)
    assert allowed is True
    assert len(called) == 0  # Callback was not invoked


def test_approval_required_denied():
    """Verify that APPROVAL_REQUIRED operations prompt callback and respect DENY decision."""
    called = []

    def deny_callback(req):
        called.append(req.tool_name)
        return DecisionType.DENY

    pm = PermissionManager(approval_callback=deny_callback, auto_allow_safe=True)

    write_req = PermissionRequest(
        request_id="req_2",
        task_id="task_1",
        permission_type=PermissionType.WRITE,
        risk_level=RiskLevel.APPROVAL_REQUIRED,
        tool_name="write_file",
        description="Write file",
        arguments={"path": "main.py", "content": "x = 1"},
        repository_path="/test/repo",
    )

    allowed = pm.check_permission(write_req)
    assert allowed is False
    assert called == ["write_file"]


def test_allow_once():
    """Verify ALLOW_ONCE allows immediate call but prompts again for next call."""
    call_count = 0

    def allow_once_callback(req):
        nonlocal call_count
        call_count += 1
        return DecisionType.ALLOW_ONCE

    pm = PermissionManager(approval_callback=allow_once_callback)

    req = PermissionRequest(
        request_id="req_3",
        task_id="task_1",
        permission_type=PermissionType.EXECUTE,
        risk_level=RiskLevel.APPROVAL_REQUIRED,
        tool_name="run_command",
        description="Run cmd",
        arguments={"command": "pytest"},
        repository_path="/test/repo",
    )

    # First call -> allowed via callback
    assert pm.check_permission(req) is True
    assert call_count == 1

    # Second call -> prompts callback again
    assert pm.check_permission(req) is True
    assert call_count == 2


def test_allow_for_task_scoping():
    """Verify ALLOW_FOR_TASK caches permission for subsequent calls within the same task."""
    call_count = 0

    def task_grant_callback(req):
        nonlocal call_count
        call_count += 1
        return DecisionType.ALLOW_FOR_TASK

    pm = PermissionManager(approval_callback=task_grant_callback)

    req_task_1 = PermissionRequest(
        request_id="req_4",
        task_id="task_A",
        permission_type=PermissionType.WRITE,
        risk_level=RiskLevel.APPROVAL_REQUIRED,
        tool_name="edit_file",
        description="Edit file",
        arguments={"path": "main.py"},
        repository_path="/test/repo",
    )

    # First call -> prompted and cached
    assert pm.check_permission(req_task_1) is True
    assert call_count == 1

    # Second call in same task -> auto-granted from task cache
    assert pm.check_permission(req_task_1) is True
    assert call_count == 1

    # Call from a different task -> prompts callback
    req_task_2 = PermissionRequest(
        request_id="req_5",
        task_id="task_B",
        permission_type=PermissionType.WRITE,
        risk_level=RiskLevel.APPROVAL_REQUIRED,
        tool_name="edit_file",
        description="Edit file",
        arguments={"path": "main.py"},
        repository_path="/test/repo",
    )
    assert pm.check_permission(req_task_2) is True
    assert call_count == 2


def test_allow_for_repo_scoping():
    """Verify ALLOW_FOR_REPO caches permission across different tasks in the same repository."""
    call_count = 0

    def repo_grant_callback(req):
        nonlocal call_count
        call_count += 1
        return DecisionType.ALLOW_FOR_REPO

    pm = PermissionManager(approval_callback=repo_grant_callback)

    req1 = PermissionRequest(
        request_id="req_6",
        task_id="task_1",
        permission_type=PermissionType.GIT,
        risk_level=RiskLevel.APPROVAL_REQUIRED,
        tool_name="git_commit",
        description="Git commit",
        arguments={"message": "fix"},
        repository_path="/repo_alpha",
    )

    # First call -> prompted and repo grant created
    assert pm.check_permission(req1) is True
    assert call_count == 1

    # Call from task_2 on same repo -> cached
    req2 = PermissionRequest(
        request_id="req_7",
        task_id="task_2",
        permission_type=PermissionType.GIT,
        risk_level=RiskLevel.APPROVAL_REQUIRED,
        tool_name="git_commit",
        description="Git commit",
        arguments={"message": "feat"},
        repository_path="/repo_alpha",
    )
    assert pm.check_permission(req2) is True
    assert call_count == 1  # No extra prompt

    # Call on different repo -> prompts callback
    req3 = PermissionRequest(
        request_id="req_8",
        task_id="task_3",
        permission_type=PermissionType.GIT,
        risk_level=RiskLevel.APPROVAL_REQUIRED,
        tool_name="git_commit",
        description="Git commit",
        arguments={"message": "init"},
        repository_path="/repo_beta",
    )
    assert pm.check_permission(req3) is True
    assert call_count == 2


def test_auto_allow_all_mode():
    """Verify auto_allow_all bypasses all prompts for testing/autonomous operation."""
    pm = PermissionManager(auto_allow_all=True)

    req = PermissionRequest(
        request_id="req_9",
        task_id="task_1",
        permission_type=PermissionType.WRITE,
        risk_level=RiskLevel.APPROVAL_REQUIRED,
        tool_name="delete_file",
        description="Delete file",
        arguments={"path": "temp.txt"},
        repository_path="/test/repo",
    )

    assert pm.check_permission(req) is True
