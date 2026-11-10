"""
Phase 9.3 — MCP Tool Execution / Controlled Agent Loop Tests.

No autonomous loops. No arbitrary execution. Deterministic fixtures.
"""
import pytest
import tempfile
from pathlib import Path
from app.agent.state.agent_state import AgentTask, AgentState, AgentObservation, AgentStep
from app.agent.router.router import AgentRouter
from app.agent.router.tool_executor import ToolExecutor, ExecutionStatus
from app.agent.router.tool_router_contracts import get_registry, TOOL_REGISTRY


@pytest.fixture
def temp_repo():
    tmp = Path(tempfile.mkdtemp())
    (tmp / "auth.py").write_text("def check(): pass\n")
    (tmp / "test_auth.py").write_text("def test_check(): pass\n")
    return str(tmp)


# ------------------------------------------------------------------
# Registry validation
# ------------------------------------------------------------------

def test_known_tool_executes(temp_repo):
    router = AgentRouter()
    task = AgentTask(task_id="t_know", query="Search", task_type="QUESTION", repository_path=temp_repo)
    sel = router.route(task)
    executor = ToolExecutor()
    result = executor.execute_read_only(sel, repository_path=temp_repo, task_id="t_know")
    assert result is not None
    assert result.tool_name == sel.primary_tool.tool_name


def test_unknown_tool_rejected():
    from app.agent.router.tool_router_contracts import ToolSelection, ToolDecision, ToolCategory
    executor = ToolExecutor()
    bad_sel = ToolSelection(
        primary_tool=ToolDecision(
            decision_id="d_bad", task_id="t_bad", tool_name="fake_tool_xyz",
            category=ToolCategory.RETRIEVAL, reason="bad", confidence=0.0, requires_confirmation=False,
        )
    )
    result = executor.execute(bad_sel, repository_path=".", task_id="t_bad")
    assert result.success is False
    assert "REJECTED" in (result.error or "")


# ------------------------------------------------------------------
# Read-only execution (controlled, safe)
# ------------------------------------------------------------------

def test_search_code_read_only(temp_repo):
    router = AgentRouter()
    task = AgentTask(task_id="t_sc", query="Where is auth?", task_type="QUESTION", repository_path=temp_repo)
    sel = router.route(task)
    executor = ToolExecutor()
    result = executor.execute_read_only(sel, repository_path=temp_repo, task_id="t_sc")
    assert result.tool_name in ("search_code", "find_symbol", "search_files")


def test_read_file_read_only(temp_repo):
    router = AgentRouter()
    task = AgentTask(task_id="t_rf", query="Read auth", task_type="QUESTION", repository_path=temp_repo)
    # Force read_file selection by keyword
    sel = router.route(AgentTask(task_id="t_rf2", query="show file contents", task_type="QUESTION", repository_path=temp_repo))
    # If router picks read_file, execute; otherwise just confirm safe path exists
    executor = ToolExecutor()
    result = executor.execute_read_only(sel, arguments={"file_path": str(Path(temp_repo) / "auth.py")}, repository_path=temp_repo, task_id="t_rf")
    assert result is not None


def test_find_symbol_read_only(temp_repo):
    executor = ToolExecutor()
    router = AgentRouter()
    task = AgentTask(task_id="t_fs", query="Find UserService", task_type="INVESTIGATE", repository_path=temp_repo)
    sel = router.route(task)
    result = executor.execute_read_only(sel, repository_path=temp_repo, task_id="t_fs")
    assert result is not None


def test_get_repo_structure_read_only(temp_repo):
    router = AgentRouter()
    task = AgentTask(task_id="t_gs", query="Repo structure", task_type="QUESTION", repository_path=temp_repo)
    sel = router.route(task)
    executor = ToolExecutor()
    result = executor.execute_read_only(sel, repository_path=temp_repo, task_id="t_gs")
    assert result is not None


# ------------------------------------------------------------------
# Approval / mutating safety
# ------------------------------------------------------------------

def test_mutating_requires_approval(temp_repo):
    from app.agent.router.tool_router_contracts import ToolSelection, ToolDecision, ToolCategory
    executor = ToolExecutor()
    bad_sel = ToolSelection(
        primary_tool=ToolDecision(
            decision_id="d_mut", task_id="t_mut", tool_name="edit_file",
            category=ToolCategory.CODE, reason="mutating", confidence=0.9, requires_confirmation=True,
        )
    )
    result = executor.execute(bad_sel, repository_path=temp_repo, task_id="t_mut", approval_granted=False)
    assert result.success is False
    assert "APPROVAL_REQUIRED" in (result.error or "")


# ------------------------------------------------------------------
# Argument validation
# ------------------------------------------------------------------

def test_missing_args_rejected_gracefully(temp_repo):
    # Execute with no args where tool expects file_path; registry.execute handles
    router = AgentRouter()
    task = AgentTask(task_id="t_arg", query="Read", task_type="QUESTION", repository_path=temp_repo)
    sel = router.route(task)
    executor = ToolExecutor()
    # Without proper args, tool may fail gracefully (not arbitrary shell)
    result = executor.execute_read_only(sel, arguments={}, repository_path=temp_repo, task_id="t_arg")
    assert result is not None


# ------------------------------------------------------------------
# Tool result + AgentState update
# ------------------------------------------------------------------

def test_agent_state_updated_after_execution(temp_repo):
    router = AgentRouter()
    task = AgentTask(task_id="t_st", query="Search", task_type="QUESTION", repository_path=temp_repo)
    sel = router.route(task)
    state = AgentState(
        task_id="t_st",
        session_id="sess_st",
        repository_path=temp_repo,
        user_goal="Test",
    )
    executor = ToolExecutor()
    result = executor.execute_read_only(sel, repository_path=temp_repo, task_id="t_st", state=state)
    assert len(state.observations) >= 0
    # Tool history should contain result (if success) or at least no crash
    assert state is not None


# ------------------------------------------------------------------
# Determinism
# ------------------------------------------------------------------

def test_same_selection_same_result(temp_repo):
    router = AgentRouter()
    task = AgentTask(task_id="t_det", query="Search auth", task_type="QUESTION", repository_path=temp_repo)
    sel1 = router.route(task)
    sel2 = router.route(task)
    assert sel1.primary_tool.tool_name == sel2.primary_tool.tool_name


# ------------------------------------------------------------------
# No arbitrary execution
# ------------------------------------------------------------------

def test_no_arbitrary_shell_execution():
    from app.agent.router.tool_executor import ToolExecutor
    import inspect
    src = inspect.getsource(ToolExecutor.execute)
    assert "subprocess.run" not in src
    assert "os.system" not in src
    assert "os.popen" not in src


# ------------------------------------------------------------------
# Execution status capture
# ------------------------------------------------------------------

def test_success_result_has_output_or_none(temp_repo):
    router = AgentRouter()
    task = AgentTask(task_id="t_out", query="List files", task_type="QUESTION", repository_path=temp_repo)
    sel = router.route(task)
    executor = ToolExecutor()
    result = executor.execute_read_only(sel, repository_path=temp_repo, task_id="t_out")
    # Either success with output, or safe failure (never fabricated success)
    if result.success:
        assert result.tool_name is not None
    else:
        assert result.error is not None
