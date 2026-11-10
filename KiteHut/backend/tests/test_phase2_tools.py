"""
Tests for Phase 2 — PRD-named tools and MCP tool layer.

Covers:
- The 7 missing PRD-named tools (list_files, find_symbol, get_repo_structure,
  get_dependencies, get_git_diff, get_git_log, run_analysis)
- Registry registration of every PRD-required tool name
- MCP server startup and tool discovery
- Representative tool execution through the MCP layer
"""

from pathlib import Path

import pytest

from app.tools.registry import create_default_tool_registry
from app.tools.phase2_tools import (
    ListFilesTool,
    FindSymbolTool,
    GetRepoStructureTool,
    GetDependenciesTool,
    GetGitDiffTool,
    GetGitLogTool,
    RunAnalysisTool,
)

PRD_REQUIRED_TOOLS = [
    "read_file",
    "list_files",
    "search_code",
    "find_symbol",
    "get_repo_structure",
    "get_dependencies",
    "get_git_diff",
    "get_git_log",
    "run_tests",
    "run_analysis",
    "edit_file",
    "git_status",
]


# ---------------------------------------------------------------------------
# Registry registration
# ---------------------------------------------------------------------------

def test_registry_contains_all_prd_required_tool_names():
    """Every PRD Phase 2 tool name must be registered."""
    registry = create_default_tool_registry()
    names = {tool.name for tool in registry.list_tools()}
    missing = [name for name in PRD_REQUIRED_TOOLS if name not in names]
    assert not missing, f"Missing PRD tools: {missing}"


def test_registry_preserves_pre_existing_tools():
    """Existing working tools must not be dropped by the Phase 2 additions."""
    registry = create_default_tool_registry()
    names = {tool.name for tool in registry.list_tools()}
    for existing in (
        "read_file",
        "write_file",
        "edit_file",
        "delete_file",
        "search_files",
        "search_code",
        "run_command",
        "run_tests",
        "run_linter",
        "run_typecheck",
        "git_status",
        "git_diff",
        "git_log",
        "git_branch",
        "git_commit",
        "git_checkout",
    ):
        assert existing in names, f"Pre-existing tool lost: {existing}"


def test_new_tools_are_read_only_safe():
    """The 7 new tools must not require approval for read-only operations."""
    registry = create_default_tool_registry()
    for name in (
        "list_files",
        "find_symbol",
        "get_repo_structure",
        "get_dependencies",
        "get_git_diff",
        "get_git_log",
        "run_analysis",
    ):
        tool = registry.get(name)
        assert tool is not None
        assert tool.risk_level.value == "SAFE", f"{name} should be SAFE"


def test_tool_schemas_are_valid():
    """Each tool must expose a usable JSON schema for LLM/MCP consumption."""
    registry = create_default_tool_registry()
    for tool in registry.list_tools():
        spec = tool.to_tool_spec()
        assert spec["type"] == "function"
        assert spec["function"]["name"] == tool.name
        assert spec["function"]["description"]
        params = spec["function"]["parameters"]
        assert params["type"] == "object"
        assert isinstance(params["properties"], dict)


# ---------------------------------------------------------------------------
# list_files
# ---------------------------------------------------------------------------

def test_list_files_returns_directory_entries(temp_workspace):
    tool = ListFilesTool()
    output = tool.run(repository_path=str(temp_workspace))
    assert "List" in output
    assert "src" in output


def test_list_files_with_pattern_filters_results(temp_workspace):
    tool = ListFilesTool()
    output = tool.run(repository_path=str(temp_workspace), pattern="*.py")
    assert "main.py" in output
    assert "README.md" not in output


def test_list_files_missing_directory_raises(temp_workspace):
    tool = ListFilesTool()
    with pytest.raises(FileNotFoundError):
        tool.run(repository_path=str(temp_workspace), path="does_not_exist")


# ---------------------------------------------------------------------------
# find_symbol
# ---------------------------------------------------------------------------

def test_find_symbol_locates_function(temp_workspace):
    tool = FindSymbolTool()
    output = tool.run(query="add", repository_path=str(temp_workspace))
    assert "add" in output
    assert "main.py" in output


def test_find_symbol_reports_no_matches(temp_workspace):
    tool = FindSymbolTool()
    output = tool.run(query="zzz_nonexistent_symbol_zzz", repository_path=str(temp_workspace))
    assert "No symbols found" in output


# ---------------------------------------------------------------------------
# get_repo_structure / get_dependencies
# ---------------------------------------------------------------------------

def test_get_repo_structure_reports_repository(temp_workspace):
    tool = GetRepoStructureTool()
    output = tool.run(repository_path=str(temp_workspace))
    assert "Repository Structure" in output
    assert "Files scanned" in output


def test_get_repo_structure_includes_symbols_when_requested(temp_workspace):
    tool = GetRepoStructureTool()
    output = tool.run(repository_path=str(temp_workspace), include_symbols=True)
    assert "Symbols" in output


def test_get_dependencies_returns_listing(temp_workspace):
    tool = GetDependenciesTool()
    output = tool.run(repository_path=str(temp_workspace))
    assert "Dependencies" in output or "No external dependencies" in output


# ---------------------------------------------------------------------------
# get_git_diff / get_git_log (PRD aliases)
# ---------------------------------------------------------------------------

def test_get_git_diff_alias_reports_no_changes(temp_git_repo):
    tool = GetGitDiffTool()
    output = tool.run(repository_path=str(temp_git_repo))
    assert "No changes detected" in output or "diff" in output.lower()


def test_get_git_log_alias_lists_commits(temp_git_repo):
    tool = GetGitLogTool()
    output = tool.run(repository_path=str(temp_git_repo), max_count=5)
    assert "Recent Commits" in output
    assert "Initial test commit" in output


# ---------------------------------------------------------------------------
# run_analysis
# ---------------------------------------------------------------------------

def test_run_analysis_executes_and_returns_result(temp_workspace):
    tool = RunAnalysisTool()
    output = tool.run(repository_path=str(temp_workspace))
    assert output
    assert "Analysis" in output


def test_run_analysis_accepts_categories(temp_workspace):
    tool = RunAnalysisTool()
    output = tool.run(repository_path=str(temp_workspace), categories=["security"])
    assert "Analysis" in output


# ---------------------------------------------------------------------------
# MCP server: startup + discovery
# ---------------------------------------------------------------------------

def test_mcp_server_starts_and_discovers_tools():
    """MCP server must construct and expose the full tool set."""
    from app.mcp.server import RepoLensMCPServer

    server = RepoLensMCPServer(repository_path=".")
    payload = server.discover()

    assert payload["server"] == "RepoLens MCP"
    assert payload["tool_count"] == len(server.get_registered_tool_names())
    assert payload["tool_count"] > 0


def test_mcp_server_exposes_all_prd_tools():
    from app.mcp.server import RepoLensMCPServer

    server = RepoLensMCPServer(repository_path=".")
    names = set(server.get_registered_tool_names())
    missing = [name for name in PRD_REQUIRED_TOOLS if name not in names]
    assert not missing, f"MCP server missing tools: {missing}"


def test_mcp_server_tool_specs_are_exposed():
    from app.mcp.server import RepoLensMCPServer

    server = RepoLensMCPServer(repository_path=".")
    specs = server.list_tool_specs()
    assert len(specs) == len(server.get_registered_tool_names())
    for spec in specs:
        assert spec["function"]["name"]


def test_mcp_server_registers_tools_with_mcp_runtime():
    """Tools must actually be registered into the underlying MCP server."""
    from app.mcp.server import RepoLensMCPServer

    server = RepoLensMCPServer(repository_path=".")
    registered = server.mcp._tool_manager.list_tools()
    names = {t.name for t in registered}
    for required in ("read_file", "list_files", "find_symbol", "get_repo_structure"):
        assert required in names, f"{required} not registered with MCP runtime"


# ---------------------------------------------------------------------------
# MCP server: representative tool execution
# ---------------------------------------------------------------------------

def test_mcp_server_executes_representative_tool(temp_workspace):
    """A tool invoked through the MCP wrapper must return real output."""
    from app.mcp.server import RepoLensMCPServer

    server = RepoLensMCPServer(repository_path=str(temp_workspace))
    result = server._wrap_tool(server.registry.get("read_file"))(
        path="README.md"
    )
    assert result["success"] is True
    assert "Test Repo" in result["output"]


def test_mcp_server_reports_tool_errors_without_raising(temp_workspace):
    from app.mcp.server import RepoLensMCPServer

    server = RepoLensMCPServer(repository_path=str(temp_workspace))
    result = server._wrap_tool(server.registry.get("read_file"))(
        path="missing_file.txt"
    )
    assert result["success"] is False
    assert result["error"]
