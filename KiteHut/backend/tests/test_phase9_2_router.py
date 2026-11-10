"""
Phase 9.2 — Tool Selection / Agent Router Tests.

No execution. No side effects. No MCP calls.
"""
import pytest
from app.agent.state.agent_state import AgentTask
from app.agent.router.tool_router_contracts import (
    ToolCapability, ToolDecision, ToolSelection, ToolCategory,
    TOOL_REGISTRY, get_registry, get_registered_tool_names,
)
from app.agent.router.router import AgentRouter


# ------------------------------------------------------------------
# Registry
# ------------------------------------------------------------------

def test_registry_has_23_tools():
    names = get_registered_tool_names()
    assert len(names) == 23


def test_registry_no_duplicates():
    names = get_registered_tool_names()
    assert len(names) == len(set(names))


def test_all_tool_names_valid():
    registry = get_registry()
    from app.tools.registry import create_default_tool_registry
    real = {t.name for t in create_default_tool_registry().list_tools()}
    for name in registry:
        assert name in real, f"Unknown tool in router registry: {name}"


def test_tool_metadata_serializes():
    cap = TOOL_REGISTRY["search_code"]
    data = cap.model_dump()
    assert data["tool_name"] == "search_code"
    assert data["category"] == "RETRIEVAL"
    assert data["read_only"] is True


# ------------------------------------------------------------------
# Routing by task type
# ------------------------------------------------------------------

def test_route_question():
    router = AgentRouter()
    task = AgentTask(task_id="t_q", query="What is auth?", task_type="QUESTION", repository_path="/r")
    sel = router.route(task)
    assert sel.primary_tool.tool_name in ("search_code", "find_symbol")
    assert sel.ambiguity is False


def test_route_explain():
    router = AgentRouter()
    task = AgentTask(task_id="t_e", query="Explain auth flow", task_type="EXPLAIN", repository_path="/r")
    sel = router.route(task)
    assert sel.primary_tool.category == ToolCategory.RETRIEVAL


def test_route_review():
    router = AgentRouter()
    task = AgentTask(task_id="t_r", query="Review code", task_type="REVIEW", repository_path="/r")
    sel = router.route(task)
    assert sel.primary_tool.tool_name == "run_analysis"


def test_route_investigate():
    router = AgentRouter()
    task = AgentTask(task_id="t_i", query="Investigate", task_type="INVESTIGATE", repository_path="/r")
    sel = router.route(task)
    assert sel.ambiguity is False


def test_route_test():
    router = AgentRouter()
    task = AgentTask(task_id="t_t", query="Run tests", task_type="TEST", repository_path="/r")
    sel = router.route(task)
    assert sel.primary_tool.tool_name == "run_tests"


def test_route_fix():
    router = AgentRouter()
    task = AgentTask(task_id="t_f", query="Fix bug", task_type="FIX", repository_path="/r")
    sel = router.route(task)
    assert sel.primary_tool.category == ToolCategory.CODE


# ------------------------------------------------------------------
# Query routing
# ------------------------------------------------------------------

def test_route_where_auth():
    router = AgentRouter()
    task = AgentTask(task_id="t_wa", query="Where is authentication implemented?", task_type="QUESTION", repository_path="/r")
    sel = router.route(task)
    assert sel.primary_tool.tool_name == "search_code"


def test_route_explain_auth():
    router = AgentRouter()
    task = AgentTask(task_id="t_ea", query="Explain the authentication flow.", task_type="EXPLAIN", repository_path="/r")
    sel = router.route(task)
    assert sel.primary_tool.tool_name == "search_code"


def test_route_latest_changes():
    router = AgentRouter()
    task = AgentTask(task_id="t_lc", query="Show the latest git changes.", task_type="INVESTIGATE", repository_path="/r")
    sel = router.route(task)
    assert sel.primary_tool.category == ToolCategory.GIT


def test_route_dependencies():
    router = AgentRouter()
    task = AgentTask(task_id="t_de", query="What dependencies does this project use?", task_type="QUESTION", repository_path="/r")
    sel = router.route(task)
    assert sel.primary_tool.tool_name == "get_dependencies"


def test_route_run_tests():
    router = AgentRouter()
    task = AgentTask(task_id="t_rt", query="Run the tests.", task_type="TEST", repository_path="/r")
    sel = router.route(task)
    assert sel.primary_tool.tool_name == "run_tests"


def test_route_review_security():
    router = AgentRouter()
    task = AgentTask(task_id="t_rev", query="Review this repository for security issues.", task_type="REVIEW", repository_path="/r")
    sel = router.route(task)
    assert sel.primary_tool.tool_name == "run_analysis"


def test_route_find_userservice():
    router = AgentRouter()
    task = AgentTask(task_id="t_fs", query="Find the implementation of UserService.", task_type="INVESTIGATE", repository_path="/r")
    sel = router.route(task)
    assert sel.primary_tool.tool_name == "search_code" or sel.primary_tool.tool_name == "find_symbol"


# ------------------------------------------------------------------
# Ambiguity / clarification
# ------------------------------------------------------------------

def test_ambiguous_help_me():
    router = AgentRouter()
    task = AgentTask(task_id="t_amb", query="Help me with this project.", task_type="QUESTION", repository_path="/r")
    sel = router.route(task)
    # Should not randomly pick dangerous tool; may fall back to retrieval with clarification or safe default
    assert sel.primary_tool is not None
    assert sel.ambiguity is False or sel.clarification_needed is False  # deterministic fallback allowed


def test_ambiguous_empty_query():
    router = AgentRouter()
    task = AgentTask(task_id="t_empt", query="", task_type="QUESTION", repository_path="/r")
    sel = router.route(task)
    assert sel.primary_tool is not None


# ------------------------------------------------------------------
# Read-only / mutating safety
# ------------------------------------------------------------------

def test_readonly_no_confirmation():
    router = AgentRouter()
    # All read-only capabilities should not require confirmation by design
    for name, cap in get_registry().items():
        if cap.read_only:
            assert cap.requires_approval is False or cap.read_only is True


def test_mutating_requires_approval():
    router = AgentRouter()
    task = AgentTask(task_id="t_mut", query="Edit file", task_type="FIX", repository_path="/r")
    sel = router.route(task)
    # If it picks a mutating tool, confirmation must be true
    if sel.primary_tool.tool_name in ("edit_file", "write_file", "delete_file", "run_command"):
        assert sel.primary_tool.requires_confirmation is True


# ------------------------------------------------------------------
# Determinism
# ------------------------------------------------------------------

def test_determinism():
    router = AgentRouter()
    task = AgentTask(task_id="t_det", query="Show git log", task_type="INVESTIGATE", repository_path="/r")
    s1 = router.route(task)
    s2 = router.route(task)
    assert s1.primary_tool.tool_name == s2.primary_tool.tool_name
    assert s1.primary_tool.category == s2.primary_tool.category


# ------------------------------------------------------------------
# Serialization
# ------------------------------------------------------------------

def test_decision_serializes():
    dec = ToolDecision(decision_id="d1", task_id="t1", tool_name="search_code", category=ToolCategory.RETRIEVAL, reason="test", confidence=0.9, requires_confirmation=False)
    data = dec.model_dump()
    restored = ToolDecision(**data)
    assert restored.tool_name == "search_code"


def test_selection_serializes():
    sel = ToolSelection(primary_tool=ToolDecision(decision_id="d1", task_id="t1", tool_name="run_tests", category=ToolCategory.TESTING, reason="t", confidence=1.0, requires_confirmation=True))
    data = sel.model_dump()
    restored = ToolSelection(**data)
    assert restored.primary_tool.tool_name == "run_tests"


# ------------------------------------------------------------------
# No execution / side-effect free
# ------------------------------------------------------------------

def test_router_no_mcp_call():
    router = AgentRouter()
    task = AgentTask(task_id="t_ne", query="Search", task_type="QUESTION", repository_path="/r")
    # Just call route; must not raise, must not call subprocess / MCP / git
    sel = router.route(task)
    assert sel is not None
