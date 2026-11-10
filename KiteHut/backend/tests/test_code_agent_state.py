"""
Phase 7 — Code Agent State Model Tests.

Tests for the deterministic state machine and patch model.
Uses temporary fixture repositories for modification tests.
Does NOT modify the user's actual project during automated tests.
"""

import hashlib
import subprocess
import tempfile
from pathlib import Path

import pytest

from app.agent.state.code_agent_state import (
    CodeAgentPlan,
    CodeAgentState,
    CodeAgentStatus,
    PatchOperation,
    ProposedPatch,
)


# ------------------------------------------------------------------
# Helper: create a temporary repo with known content
# ------------------------------------------------------------------
def _git(repo: Path, *args):
    subprocess.run(["git", *args], cwd=repo, capture_output=True)


@pytest.fixture
def temp_repo():
    """Create a temporary git repository with test files."""
    tmp = Path(tempfile.mkdtemp())
    _git(tmp, "init")
    _git(tmp, "config", "user.email", "test@repolens.test")
    _git(tmp, "config", "user.name", "Test")

    (tmp / "example.py").write_text('password = "hardcoded_secret"\n')
    _git(tmp, "add", ".")
    _git(tmp, "commit", "-m", "Initial commit")

    (tmp / "config.py").write_text('API_KEY = "sk-test-12345"\n')
    _git(tmp, "add", ".")
    _git(tmp, "commit", "-m", "Initial commit 2")

    yield tmp

    import shutil
    shutil.rmtree(tmp, ignore_errors=True)


# ------------------------------------------------------------------
# ProposedPatch Tests
# ------------------------------------------------------------------


def test_proposed_patch_creation():
    """Test that a ProposedPatch can be created with all fields."""
    patch = ProposedPatch(
        file_path="app/example.py",
        operation=PatchOperation.MODIFY,
        old_content="# old content\npassword = 'secret'\n",
        new_content="# new content\nAPI_KEY = 'env_var'\n",
        reason="Fix authentication token validation",
        snippet="# Fix: credential moved to environment variable",
    )
    assert patch.file_path == "app/example.py"
    assert patch.operation == PatchOperation.MODIFY
    assert patch.reason == "Fix authentication token validation"
    assert patch.snippet == "# Fix: credential moved to environment variable"
    assert patch.old_hash is None


def test_proposed_patch_create_operation():
    """Test ProposedPatch with CREATE operation."""
    patch = ProposedPatch(
        file_path="app/new_file.py",
        operation=PatchOperation.CREATE,
        new_content="# New file created by CodeAgent",
        reason="Add new utility module",
    )
    assert patch.operation == PatchOperation.CREATE
    assert patch.file_path == "app/new_file.py"


def test_proposed_patch_old_hash_validation():
    """Test that old_hash-based staleness detection works correctly."""
    current = 'password = "secret"\n'
    old_hash = hashlib.sha256(current.encode("utf-8")).hexdigest()

    patch = ProposedPatch(
        file_path="app/example.py",
        operation=PatchOperation.MODIFY,
        old_content=current,
        old_hash=old_hash,
        new_content='API_KEY = "env_var"\n',
        reason="Move credential to environment variable",
    )

    # Matching hash → not stale
    assert patch.is_stale(current) is False

    # Mismatched content → stale
    assert patch.is_stale('other = "value"\n') is True


def test_proposed_patch_content_staleness():
    """Test staleness detection using old_content (no hash)."""
    patch = ProposedPatch(
        file_path="app/example.py",
        operation=PatchOperation.MODIFY,
        old_content='password = "secret"\n',
        new_content='API_KEY = "env_var"\n',
        reason="Move credential",
    )
    assert patch.is_stale('password = "secret"\n') is False
    assert patch.is_stale('password = "changed"\n') is True


def test_proposed_patch_no_baseline_is_stale():
    """A patch with no recorded baseline cannot be validated → stale."""
    patch = ProposedPatch(
        file_path="app/example.py",
        operation=PatchOperation.CREATE,
        new_content="x = 1\n",
        reason="New file",
    )
    assert patch.is_stale("anything") is True


# ------------------------------------------------------------------
# CodeAgentState Tests
# ------------------------------------------------------------------


def test_code_agent_state_initialized():
    """Test CodeAgentState initializes in REQUESTED status."""
    state = CodeAgentState(
        task_id="test_123",
        session_id="sess_abc",
        repository_path="/tmp/test",
        user_goal="Fix hardcoded credential",
    )
    assert state.status == CodeAgentStatus.REQUESTED
    assert state.task_id == "test_123"
    assert state.repository_path == "/tmp/test"
    assert state.user_goal == "Fix hardcoded credential"
    assert state.approval_status is None
    assert state.proposed_patch is None
    assert state.applied_changes == {}
    assert state.retry_count == 0
    assert state.max_retries == 3


def test_code_agent_state_transitions():
    """Test status transitions through the workflow."""
    state = CodeAgentState(
        task_id="test_456",
        session_id="sess_def",
        repository_path="/tmp/test",
        user_goal="Fix authentication issue",
    )

    for status in (
        CodeAgentStatus.REQUESTED,
        CodeAgentStatus.INVESTIGATING,
        CodeAgentStatus.PLANNED,
        CodeAgentStatus.PATCH_PROPOSED,
        CodeAgentStatus.AWAITING_APPROVAL,
        CodeAgentStatus.APPROVED,
        CodeAgentStatus.APPLYING,
        CodeAgentStatus.TESTING,
        CodeAgentStatus.REVIEWING,
        CodeAgentStatus.VERIFYING,
        CodeAgentStatus.COMPLETED,
    ):
        state.status = status
        assert state.status == status


def test_code_agent_state_approval_boundary():
    """Test that an unapproved patch cannot be applied."""
    state = CodeAgentState(
        task_id="test_789",
        session_id="sess_ghi",
        repository_path="/tmp/test",
        user_goal="Test approval boundary",
    )

    # Initially cannot apply patch (no approval)
    assert not state.can_apply_patch()

    # Even after proposing a patch, still cannot apply without approval
    patch = ProposedPatch(
        file_path="app/test.py",
        operation=PatchOperation.MODIFY,
        old_content="# old",
        new_content="# new",
        reason="Test",
    )
    state.proposed_patch = patch
    assert not state.can_apply_patch()

    # After explicit approval, can apply
    state.approval_status = "approved"
    assert state.can_apply_patch()

    # A rejected patch cannot apply
    state.approval_status = "rejected"
    assert not state.can_apply_patch()


def test_code_agent_state_can_retry():
    """Test retry count is bounded."""
    state = CodeAgentState(
        task_id="test_retry",
        session_id="sess_jkl",
        repository_path="/tmp/test",
        user_goal="Test retry bound",
        max_retries=3,
    )

    assert state.can_retry()

    state.retry_count = 3
    assert not state.can_retry()

    state.retry_count = 0
    assert state.can_retry()


def test_code_agent_state_mark_helpers():
    """Test marking reviewed/verified/completed/failed/cancelled."""
    state = CodeAgentState(
        task_id="test_mark",
        session_id="sess_mno",
        repository_path="/tmp/test",
        user_goal="Test marking",
    )

    state.status = CodeAgentStatus.TESTING
    state.mark_reviewed()
    assert state.status == CodeAgentStatus.REVIEWING

    state.mark_verified()
    assert state.status == CodeAgentStatus.VERIFYING

    state.mark_completed()
    assert state.status == CodeAgentStatus.COMPLETED

    state.mark_failed("Test error message")
    assert state.status == CodeAgentStatus.FAILED
    assert state.error_message == "Test error message"

    state.mark_cancelled()
    assert state.status == CodeAgentStatus.CANCELLED


def test_code_agent_state_with_plan():
    """Test CodeAgentState with a full plan."""
    state = CodeAgentState(
        task_id="plan_test",
        session_id="sess_plan",
        repository_path="/tmp/test",
        user_goal="Add new authentication module",
    )

    state.plan = CodeAgentPlan(
        task_id="plan_test",
        goal="Add new authentication module",
        steps=[
            {
                "step_id": 1,
                "description": "Search for auth-related code",
                "tool_name": "search_code",
                "expected_output": "Auth code locations identified",
            },
            {
                "step_id": 2,
                "description": "Read current authentication file",
                "tool_name": "read_file",
                "expected_output": "Auth code read",
            },
            {
                "step_id": 3,
                "description": "Create new authentication module",
                "tool_name": "write_file",
                "expected_output": "New module created",
            },
            {
                "step_id": 4,
                "description": "Run tests to verify new module",
                "tool_name": "run_tests",
                "expected_output": "Tests pass",
            },
        ],
    )

    assert state.plan is not None
    assert len(state.plan.steps) == 4
    assert state.plan.status == CodeAgentStatus.PLANNED
    assert state.plan.created_at is not None


def test_code_agent_state_applied_changes():
    """Test that applied_changes tracks modifications."""
    state = CodeAgentState(
        task_id="changes_test",
        session_id="sess_changes",
        repository_path="/tmp/test",
        user_goal="Test applied changes tracking",
    )

    assert state.applied_changes == {}

    state.applied_changes["app/test.py"] = "new content here"
    state.applied_changes["app/utils.py"] = "more content"
    assert "app/test.py" in state.applied_changes
    assert "app/utils.py" in state.applied_changes
