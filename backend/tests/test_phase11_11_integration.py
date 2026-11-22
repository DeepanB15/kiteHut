"""Phase 11.11 — Agent & MCP integration focused tests.

Covers the read-only Code Graph tools, graph-guided Smart Context retrieval,
evidence-backed claim verification, permission/containment behavior and MCP
registration.  The tests use small throwaway repositories and never start a
server or modify the project repository.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.agent.permissions.manager import PermissionManager
from app.agent.permissions.policies import PermissionType, RiskLevel
from app.agent.router.router import AgentRouter
from app.agent.router.tool_executor import ToolExecutor
from app.agent.state.agent_state import AgentTask
from app.chunking.repository_chunker import chunk_repo
from app.code_graph import CodeGraphBuilder
from app.code_graph.integration import (
    _align_candidates_to_chunks,
    integrate_graph_into_retrieval,
    merge_graph_candidates,
)
from app.mcp.server import RepoLensMCPServer
from app.retrieval.hybrid.retrieval import HybridRetrievalResult, HybridRetriever
from app.tools import code_graph_tools
from app.tools.base import BaseTool
from app.tools.registry import ToolRegistry, create_default_tool_registry

FIXTURE_PROJECT = Path(__file__).parent / "fixtures" / "code_graph" / "sample_project"
GRAPH_TOOL_NAMES = {
    "graph_find_symbol",
    "graph_callers",
    "graph_callees",
    "graph_imports",
    "graph_dependents",
    "graph_impact",
    "graph_context",
    "verify_claim",
}


def _write(root: Path, relative_path: str, content: str) -> Path:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "sample_project"
    for relative in ("__init__.py", "pkg/__init__.py", "pkg/core.py", "pkg/util.py"):
        source = FIXTURE_PROJECT / relative
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    return root


@pytest.fixture()
def duplicate_repo(tmp_path: Path) -> Path:
    root = tmp_path / "duplicate_repo"
    _write(root, "pkg/__init__.py", "from pkg.one import helper\nfrom pkg.two import helper\n")
    _write(root, "pkg/one.py", "def helper():\n    return 1\n")
    _write(root, "pkg/two.py", "def helper():\n    return 2\n")
    return root


@pytest.fixture()
def partial_repo(tmp_path: Path) -> Path:
    root = tmp_path / "partial_repo"
    _write(root, "good.py", "def good():\n    return 1\n")
    _write(root, "broken.py", "def broken(:\n    return 2\n")
    _write(root, "unresolved.py", "from good import missing_name\n")
    return root


class _WorkspaceProbeTool(BaseTool):
    """Test-only tool that records the arguments it actually receives."""

    name = "workspace_probe"
    description = "Records the execution workspace it was given."
    permission_type = PermissionType.READ
    risk_level = RiskLevel.SAFE

    def __init__(self) -> None:
        self.seen: dict = {}

    def get_parameter_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "repository_path": {"type": "string"},
                "marker": {"type": "string"},
            },
            "required": [],
        }

    def run(self, **kwargs) -> str:
        self.seen = dict(kwargs)
        return json.dumps({"ok": True})


def _invoke(name: str, args: dict, repository_path: Path, permissions=None) -> dict:
    registry = create_default_tool_registry()
    manager = permissions or PermissionManager(auto_allow_safe=True)
    result = registry.execute(
        tool_name=name,
        arguments=args,
        repository_path=str(repository_path),
        permission_manager=manager,
        task_id="phase11_11_test",
    )
    assert result.success, result.error
    return json.loads(result.output)


# ---------------------------------------------------------------------------
# Code Graph tools
# ---------------------------------------------------------------------------


def test_graph_find_symbol_success(repo: Path) -> None:
    payload = _invoke("graph_find_symbol", {"query": "main"}, repo)

    assert payload["count"] == 1
    assert payload["ambiguous"] is False
    symbol = payload["matches"][0]
    assert symbol["qualified_name"] == "pkg/core.main"
    assert symbol["kind"] == "function"
    assert symbol["relative_path"] == "pkg/core.py"
    assert symbol["start_line"] <= symbol["end_line"]
    assert payload["graph"]["available"] is True


def test_graph_find_symbol_missing(repo: Path) -> None:
    payload = _invoke("graph_find_symbol", {"query": "does_not_exist_xyz"}, repo)

    assert payload["count"] == 0
    assert payload["matches"] == []
    assert payload["match_type"] == "partial"


def test_graph_find_symbol_reports_duplicate_names(duplicate_repo: Path) -> None:
    payload = _invoke("graph_find_symbol", {"query": "helper"}, duplicate_repo)

    assert payload["count"] == 2
    assert payload["ambiguous"] is True
    assert {match["relative_path"] for match in payload["matches"]} == {
        "pkg/one.py",
        "pkg/two.py",
    }


def test_graph_callers_and_callees(repo: Path) -> None:
    callers_payload = _invoke("graph_callers", {"symbol": "run"}, repo)
    assert callers_payload["symbol_found"] is True
    caller_names = {
        entry["node"]["name"] for entry in callers_payload["relationships"]
    }
    assert {"main", "go"} <= caller_names
    assert all(entry["direction"] == "caller" for entry in callers_payload["relationships"])
    assert callers_payload["diagnostics"]["ambiguous_edges"] == 0

    callees_payload = _invoke("graph_callees", {"symbol": "main"}, repo)
    callee_names = {
        entry["node"]["name"] for entry in callees_payload["relationships"]
    }
    assert "run" in callee_names


def test_graph_callers_ambiguous_symbol_does_not_guess(duplicate_repo: Path) -> None:
    payload = _invoke("graph_callers", {"symbol": "helper"}, duplicate_repo)

    assert payload["ambiguous"] is True
    assert payload["relationships"] == []
    assert len(payload["candidates"]) == 2


def test_graph_imports_and_dependents(repo: Path) -> None:
    imported = _invoke("graph_imports", {"path": "pkg/core.py"}, repo)
    assert imported["file_found"] is True
    imported_paths = {
        entry["node"]["relative_path"] for entry in imported["relationships"]
    }
    assert imported_paths == {"pkg/util.py"}

    dependents_payload = _invoke("graph_dependents", {"path": "pkg/util.py"}, repo)
    dependent_paths = {
        entry["node"]["relative_path"]
        for entry in dependents_payload["relationships"]
    }
    assert dependent_paths == {"pkg/core.py"}


def test_import_relationships_distinguish_unresolved(partial_repo: Path) -> None:
    payload = _invoke("graph_imports", {"path": "unresolved.py"}, partial_repo)

    assert payload["file_found"] is True
    assert payload["diagnostics"]["unresolved_import_count"] >= 1
    assert payload["diagnostics"]["unresolved_imports"]


def test_traversal_depth_and_result_limit_are_bounded(repo: Path) -> None:
    payload = _invoke(
        "graph_callers", {"symbol": "run", "depth": 99, "limit": 1}, repo
    )

    assert payload["depth"] == 3
    assert payload["count"] == 1
    assert payload["truncated"] is True
    assert all(entry["depth"] <= 3 for entry in payload["relationships"])


def test_graph_tools_survive_unavailable_graph(monkeypatch, repo: Path) -> None:
    def boom(self):  # pragma: no cover - exercised through monkeypatch
        raise RuntimeError("graph build exploded")

    monkeypatch.setattr(code_graph_tools.CodeGraphBuilder, "build", boom)

    payload = _invoke("graph_find_symbol", {"query": "main"}, repo)
    assert payload["graph"]["available"] is False
    assert payload["count"] == 0
    assert "exploded" in (payload["graph"]["error"] or "")

    callers_payload = _invoke("graph_callers", {"symbol": "run"}, repo)
    assert callers_payload["relationships"] == []
    assert callers_payload["graph"]["available"] is False


def test_partial_graph_remains_usable(partial_repo: Path) -> None:
    payload = _invoke("graph_find_symbol", {"query": "good.good"}, partial_repo)

    assert payload["graph"]["available"] is True
    assert payload["graph"]["status"] == "partial"
    assert payload["count"] == 1


def test_graph_impact_is_navigation_only(repo: Path) -> None:
    payload = _invoke("graph_impact", {"target": "run"}, repo)

    assert payload["navigation_only"] is True
    assert payload["runtime_impact_verified"] is False
    assert payload["count"] >= 1
    assert "navigation evidence" in payload["disclaimer"]


# ---------------------------------------------------------------------------
# Smart Context integration
# ---------------------------------------------------------------------------


def test_graph_context_reaches_existing_retrieval(repo: Path) -> None:
    payload = _invoke("graph_context", {"query": "helper", "limit": 10}, repo)

    assert payload["graph"]["available"] is True
    assert payload["retrieval_diagnostics"]["graph_available"] is True
    assert payload["retrieval_diagnostics"]["graph_candidates_found"] >= 1
    assert payload["count"] > 0
    chunk_ids = [candidate["chunk_id"] for candidate in payload["candidates"]]
    assert len(chunk_ids) == len(set(chunk_ids))
    scores = [candidate["final_score"] for candidate in payload["candidates"]]
    assert scores == sorted(scores, reverse=True)


def test_graph_context_keeps_keyword_candidates(repo: Path) -> None:
    payload = _invoke("graph_context", {"query": "imported_call", "limit": 20}, repo)

    keyword_hits = [
        candidate for candidate in payload["candidates"] if candidate["keyword_score"] > 0
    ]
    assert keyword_hits, "existing keyword retrieval results must remain available"
    assert any(candidate["file_path"] == "pkg/core.py" for candidate in keyword_hits)


def test_graph_context_deduplicates_against_retrieval(repo: Path) -> None:
    payload = _invoke("graph_context", {"query": "run", "limit": 20}, repo)
    diagnostics = payload["retrieval_diagnostics"]

    assert diagnostics["graph_candidates_merged"] >= 1
    assert diagnostics["graph_score_adjustments"] >= 1
    chunk_ids = [candidate["chunk_id"] for candidate in payload["candidates"]]
    assert len(chunk_ids) == len(set(chunk_ids))

    # The graph-named symbol must appear once, not once per identity system.
    run_hits = [
        candidate
        for candidate in payload["candidates"]
        if candidate["symbol_name"] == "run"
        and candidate["file_path"] == "pkg/core.py"
    ]
    assert len(run_hits) == 1


def test_graph_context_preserves_existing_candidates_and_provenance(
    repo: Path,
) -> None:
    payload = _invoke("graph_context", {"query": "imported_call", "limit": 20}, repo)
    diagnostics = payload["retrieval_diagnostics"]

    assert any(
        candidate["keyword_score"] > 0 for candidate in payload["candidates"]
    ), "existing keyword retrieval results must remain available"
    assert (
        diagnostics["retrieval_candidates_after_merge"]
        >= diagnostics["retrieval_candidates_before_merge"]
    )
    provenance = diagnostics["graph_candidate_provenance"]
    assert provenance
    assert all(entry.get("source_file") for entry in provenance.values())


def test_graph_context_imports_are_anchored_on_declaring_file(repo: Path) -> None:
    payload = _invoke("graph_context", {"query": "imported_call", "limit": 20}, repo)

    assert any(
        candidate["file_path"] == "pkg/util.py"
        for candidate in payload["candidates"]
    ), "imports of the declaring file are additive graph candidates"


def test_graph_context_without_graph_matches_existing_retrieval(repo: Path) -> None:
    chunks = [chunk for chunk_list in chunk_repo(str(repo)) for chunk in chunk_list.chunks]
    baseline = HybridRetriever(chunks=chunks).retrieve(query="run", top_k=20)

    merged, diagnostics = integrate_graph_into_retrieval("run", None, chunks)

    assert diagnostics["fallback_used"] is True
    assert [(result.chunk_id, result.final_score) for result in merged] == [
        (result.chunk_id, result.final_score) for result in baseline
    ]


def test_merge_graph_candidates_does_not_mutate_inputs() -> None:
    original = HybridRetrievalResult(
        chunk_id="chunk_1",
        final_score=0.15,
        keyword_score=0.5,
        symbol_score=0.0,
    )

    merged = merge_graph_candidates(
        [original],
        [
            {
                "chunk_id": "chunk_1",
                "graph_score": 1.0,
                "symbol_name": "run",
                "file_path": "pkg/core.py",
                "symbol_type": "function",
                "start_line": 5,
                "end_line": 6,
                "content_hash": "abc",
            }
        ],
    )

    assert original.symbol_score == 0.0
    assert original.final_score == 0.15
    assert merged[0].symbol_score == 1.0
    assert merged[0].final_score > original.final_score


def test_graph_context_bounds_repository_chunking(repo: Path) -> None:
    payload = _invoke(
        "graph_context", {"query": "run", "limit": 5, "max_files": 1}, repo
    )

    assert payload["chunks"]["files_chunked"] == 1
    assert payload["chunks"]["max_files"] == 1


def test_graph_context_falls_back_without_graph(monkeypatch, repo: Path) -> None:
    def boom(self):
        raise RuntimeError("graph unavailable")

    monkeypatch.setattr(code_graph_tools.CodeGraphBuilder, "build", boom)

    payload = _invoke("graph_context", {"query": "main"}, repo)

    assert payload["graph"]["available"] is False
    assert payload["fallback_used"] is True
    assert payload["count"] > 0


# ---------------------------------------------------------------------------
# Evidence Engine integration
# ---------------------------------------------------------------------------


def _claim_args(**overrides) -> dict:
    args = {
        "claim": "main calls run",
        "claim_type": "GENERIC",
        "target_file": "pkg/core.py",
        "target_line": 12,
        "expected_pattern": "return run()",
    }
    args.update(overrides)
    return args


def test_verify_claim_supported(repo: Path) -> None:
    payload = _invoke("verify_claim", _claim_args(), repo)

    assert payload["status"] == "SUPPORTED"
    assert payload["verdict"]["status"] == "TRUE"
    assert payload["evidence_summary"]
    assert any(
        span["relationship"] == "claim_target" and span["exact_match"]
        for span in payload["evidence_summary"]
    )


def test_verify_claim_unsupported_for_absent_existence_target(repo: Path) -> None:
    payload = _invoke(
        "verify_claim",
        _claim_args(
            claim_type="FILE_EXISTS",
            target_file="pkg/missing.py",
            target_line=None,
            expected_pattern=None,
        ),
        repo,
    )

    assert payload["status"] == "UNSUPPORTED"
    assert payload["verdict"]["status"] == "FALSE"


def test_verify_claim_inconclusive_for_missing_content_target(repo: Path) -> None:
    payload = _invoke(
        "verify_claim",
        _claim_args(target_file="pkg/missing.py", expected_pattern="whatever"),
        repo,
    )

    # Missing evidence is not the same as contradictory evidence.
    assert payload["status"] == "INCONCLUSIVE"
    assert payload["verdict"]["status"] == "FALSE"


def test_verify_claim_inconclusive_when_pattern_absent(repo: Path) -> None:
    payload = _invoke(
        "verify_claim",
        _claim_args(expected_pattern="return definitely_not_present()"),
        repo,
    )

    assert payload["status"] == "INCONCLUSIVE"
    assert payload["status"] in {"SUPPORTED", "UNSUPPORTED", "INCONCLUSIVE"}


def test_verify_claim_without_source_never_supported(repo: Path) -> None:
    payload = _invoke(
        "verify_claim",
        {"claim": "run is called from main", "claim_type": "GENERIC"},
        repo,
    )

    assert payload["status"] in {"UNSUPPORTED", "INCONCLUSIVE"}
    assert payload["status"] != "SUPPORTED"
    assert payload["source_locations"]
    assert all(
        not span["corroborating"]
        for span in payload["evidence_summary"]
        if span["navigation_only"]
    )


def test_stale_graph_snapshot_cannot_support_claim(monkeypatch, repo: Path) -> None:
    result = CodeGraphBuilder(repo).build()
    assert result.graph is not None
    access = code_graph_tools._GraphAccess(
        root=repo, result=result, graph=result.graph
    )

    # Mutate the file after the graph snapshot was taken.
    core = repo / "pkg" / "core.py"
    core.write_text(
        core.read_text(encoding="utf-8") + "\n# drift\n", encoding="utf-8"
    )

    monkeypatch.setattr(code_graph_tools, "_load_graph", lambda root: access)
    payload = _invoke("verify_claim", _claim_args(), repo)

    assert payload["status"] != "SUPPORTED"
    assert any(span["stale"] for span in payload["evidence_summary"])


def test_verify_claim_rejects_traversal_target_file(repo: Path) -> None:
    registry = create_default_tool_registry()
    result = registry.execute(
        "verify_claim",
        _claim_args(target_file="../../outside.py"),
        repository_path=str(repo),
        permission_manager=PermissionManager(auto_allow_safe=True),
    )

    assert result.success is False
    assert "traversal" in (result.error or "").lower()


def test_verify_claim_rejects_out_of_workspace_target_file(repo: Path) -> None:
    outside = repo.parent / "outside.py"
    outside.write_text("def outside():\n    return 1\n", encoding="utf-8")

    registry = create_default_tool_registry()
    result = registry.execute(
        "verify_claim",
        _claim_args(target_file=str(outside)),
        repository_path=str(repo),
        permission_manager=PermissionManager(auto_allow_safe=True),
    )

    assert result.success is False
    assert "outside repository" in (result.error or "").lower()


def test_verify_claim_rejects_invalid_claim_type(repo: Path) -> None:
    registry = create_default_tool_registry()
    result = registry.execute(
        "verify_claim",
        _claim_args(claim_type="NOT_A_CLAIM"),
        repository_path=str(repo),
        permission_manager=PermissionManager(auto_allow_safe=True),
    )

    assert result.success is False
    assert "claim_type" in (result.error or "")


# ---------------------------------------------------------------------------
# Agent routing / execution
# ---------------------------------------------------------------------------


def test_router_selects_graph_tools(repo: Path) -> None:
    router = AgentRouter()

    cases = {
        "Who calls run?": "graph_callers",
        "Show the callees of main": "graph_callees",
        "What are the dependents of pkg/util.py?": "graph_dependents",
        "Show imports for pkg/core.py": "graph_imports",
        "What is the impact of changing run?": "graph_impact",
        "Please verify this claim with evidence": "verify_claim",
        "Find the symbol main": "graph_find_symbol",
    }
    for query, expected in cases.items():
        task = AgentTask(
            task_id="t_route",
            query=query,
            task_type="QUESTION",
            repository_path=str(repo),
        )
        selection = router.route(task)
        assert selection.primary_tool.tool_name == expected

    unrelated = AgentTask(
        task_id="t_plain",
        query="Where is authentication implemented?",
        task_type="QUESTION",
        repository_path=str(repo),
    )
    assert router.route(unrelated).primary_tool.tool_name == "search_code"


def test_executor_runs_graph_tool_through_existing_boundary(repo: Path) -> None:
    router = AgentRouter()
    executor = ToolExecutor()
    task = AgentTask(
        task_id="t_exec_graph",
        query="Who calls run?",
        task_type="QUESTION",
        repository_path=str(repo),
    )
    result = executor.execute_read_only(
        router.route(task), repository_path=str(repo), task_id=task.task_id
    )

    assert result.success is True
    payload = json.loads(result.output)
    assert payload["symbol_found"] is True
    assert payload["count"] == 2


def test_agent_can_locate_symbol_end_to_end(repo: Path) -> None:
    router = AgentRouter()
    executor = ToolExecutor()
    task = AgentTask(
        task_id="t_locate",
        query="Find the symbol main",
        task_type="QUESTION",
        repository_path=str(repo),
    )
    selection = router.route(task)
    assert selection.primary_tool.tool_name == "graph_find_symbol"
    assert selection.primary_tool.suggested_arguments == {"query": "main"}

    result = executor.execute_read_only(
        selection, repository_path=str(repo), task_id=task.task_id
    )

    assert result.success is True, result.error
    payload = json.loads(result.output)
    assert payload["count"] == 1
    assert payload["matches"][0]["qualified_name"] == "pkg/core.main"


def test_graph_tools_are_read_only_and_safe() -> None:
    registry = create_default_tool_registry()
    for name in GRAPH_TOOL_NAMES:
        tool = registry.get(name)
        assert tool is not None
        assert tool.risk_level.value == "SAFE"
        assert tool.permission_type.value == "READ"
        schema = tool.get_parameter_schema()
        assert "repository_path" in schema["properties"]


# ---------------------------------------------------------------------------
# Security / containment
# ---------------------------------------------------------------------------


def test_invalid_repository_path_is_rejected(repo: Path) -> None:
    registry = create_default_tool_registry()
    result = registry.execute(
        "graph_find_symbol",
        {"query": "main"},
        repository_path=str(repo / "does_not_exist"),
        permission_manager=PermissionManager(auto_allow_safe=True),
    )

    assert result.success is False
    assert "does not exist" in (result.error or "")


def test_path_traversal_is_rejected(repo: Path) -> None:
    registry = create_default_tool_registry()
    result = registry.execute(
        "graph_imports",
        {"path": "../../outside.py"},
        repository_path=str(repo),
        permission_manager=PermissionManager(auto_allow_safe=True),
    )

    assert result.success is False
    assert "traversal" in (result.error or "").lower()


def test_absolute_out_of_workspace_path_is_rejected(repo: Path) -> None:
    outside = (repo.parent / "outside.py")
    outside.write_text("def outside():\n    return 1\n", encoding="utf-8")

    registry = create_default_tool_registry()
    result = registry.execute(
        "graph_imports",
        {"path": str(outside)},
        repository_path=str(repo),
        permission_manager=PermissionManager(auto_allow_safe=True),
    )

    assert result.success is False
    assert "outside repository" in (result.error or "").lower()


def test_filesystem_root_is_not_a_workspace() -> None:
    root = Path("/") if Path("/").parent == Path("/") else Path.cwd().anchor
    registry = create_default_tool_registry()
    result = registry.execute(
        "graph_find_symbol",
        {"query": "main"},
        repository_path=str(root),
        permission_manager=PermissionManager(auto_allow_safe=True),
    )

    assert result.success is False
    assert "filesystem root" in (result.error or "").lower() or "workspace" in (
        result.error or ""
    ).lower()


def test_graph_tools_do_not_mutate_the_repository(repo: Path) -> None:
    def snapshot() -> dict:
        return {
            path.relative_to(repo).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(repo.rglob("*"))
            if path.is_file()
        }

    before = snapshot()
    _invoke("graph_find_symbol", {"query": "main"}, repo)
    _invoke("graph_callers", {"symbol": "run"}, repo)
    _invoke("graph_imports", {"path": "pkg/core.py"}, repo)
    _invoke("graph_dependents", {"path": "pkg/util.py"}, repo)
    _invoke("graph_impact", {"target": "run"}, repo)
    _invoke("graph_context", {"query": "helper", "limit": 5}, repo)
    _invoke("verify_claim", _claim_args(), repo)

    assert snapshot() == before


def test_permission_checks_cannot_be_bypassed(repo: Path) -> None:
    registry = create_default_tool_registry()
    strict = PermissionManager(auto_allow_safe=False, approval_callback=None)

    result = registry.execute(
        "graph_find_symbol",
        {"query": "main"},
        repository_path=str(repo),
        permission_manager=strict,
    )

    assert result.success is False
    assert "permission denied" in (result.error or "").lower()


# ---------------------------------------------------------------------------
# MCP integration
# ---------------------------------------------------------------------------


def test_mcp_registers_graph_tools_once(repo: Path) -> None:
    server = RepoLensMCPServer(repository_path=str(repo))
    names = server.get_registered_tool_names()

    assert GRAPH_TOOL_NAMES <= set(names)
    assert len(names) == len(set(names))

    runtime_names = {tool.name for tool in server.mcp._tool_manager.list_tools()}
    assert GRAPH_TOOL_NAMES <= runtime_names
    specs = server.list_tool_specs()
    assert len(specs) == len(names)


def test_mcp_wrapper_returns_structured_output(repo: Path) -> None:
    server = RepoLensMCPServer(repository_path=str(repo))
    wrapper = server._wrap_tool(server.registry.get("graph_find_symbol"))

    response = wrapper(query="main")

    assert response["success"] is True
    assert response["data"]["count"] == 1
    assert response["data"]["matches"][0]["relative_path"] == "pkg/core.py"


def test_mcp_cannot_widen_repository_scope(tmp_path: Path) -> None:
    server_root = tmp_path / "server_root"
    other_root = tmp_path / "other_root"
    _write(server_root, "only_here.py", "def server_symbol():\n    return 1\n")
    _write(other_root, "elsewhere.py", "def other_symbol():\n    return 2\n")

    server = RepoLensMCPServer(repository_path=str(server_root))
    wrapper = server._wrap_tool(server.registry.get("graph_find_symbol"))

    response = wrapper(query="other_symbol", repository_path=str(other_root))

    assert response["success"] is True
    assert response["data"]["graph"]["repository_id"] is not None
    assert response["data"]["count"] == 0


def test_mcp_existing_tool_still_works(repo: Path) -> None:
    server = RepoLensMCPServer(repository_path=str(repo))
    wrapper = server._wrap_tool(server.registry.get("read_file"))

    response = wrapper(path="pkg/core.py")

    assert response["success"] is True
    assert "def main" in response["output"]


# ---------------------------------------------------------------------------
# Trusted workspace boundary and Smart Context alignment
# ---------------------------------------------------------------------------


def test_registry_rejects_repository_path_override(tmp_path: Path) -> None:
    trusted = tmp_path / "trusted"
    other = tmp_path / "other"
    trusted.mkdir()
    other.mkdir()

    probe = _WorkspaceProbeTool()
    registry = ToolRegistry()
    registry.register(probe)

    result = registry.execute(
        "workspace_probe",
        {"repository_path": str(other), "marker": "preserved"},
        repository_path=str(trusted),
        permission_manager=PermissionManager(auto_allow_safe=True),
    )

    assert result.success is True
    assert probe.seen["repository_path"] == str(trusted)
    assert probe.seen["marker"] == "preserved"


def test_alignment_prefers_exact_span_over_duplicate_symbol_names() -> None:
    chunks = [
        SimpleNamespace(
            chunk_id="chunk_a",
            file_path="pkg/x.py",
            symbol_name="helper",
            start_line=1,
            end_line=2,
        ),
        SimpleNamespace(
            chunk_id="chunk_b",
            file_path="pkg/x.py",
            symbol_name="helper",
            start_line=10,
            end_line=11,
        ),
    ]
    candidates = [
        {
            "chunk_id": "symbol:v1:aaa",
            "file_path": "pkg/x.py",
            "symbol_name": "helper",
            "start_line": 10,
            "end_line": 11,
            "graph_score": 1.0,
        }
    ]

    aligned = _align_candidates_to_chunks(candidates, chunks)

    assert aligned[0]["chunk_id"] == "chunk_b"
    assert aligned[0]["graph_chunk_id"] == "symbol:v1:aaa"


def test_alignment_keeps_ambiguous_candidates_independent() -> None:
    chunks = [
        SimpleNamespace(
            chunk_id="chunk_a",
            file_path="pkg/x.py",
            symbol_name="helper",
            start_line=1,
            end_line=2,
        ),
        SimpleNamespace(
            chunk_id="chunk_b",
            file_path="pkg/x.py",
            symbol_name="helper",
            start_line=10,
            end_line=11,
        ),
    ]
    candidates = [
        {
            "chunk_id": "symbol:v1:ccc",
            "file_path": "pkg/x.py",
            "symbol_name": "helper",
            "start_line": 30,
            "end_line": 31,
            "graph_score": 0.8,
        }
    ]

    aligned = _align_candidates_to_chunks(candidates, chunks)

    # No exact span and more than one same-name chunk: never guess.
    assert aligned[0]["chunk_id"] == "symbol:v1:ccc"
    assert "graph_chunk_id" not in aligned[0]


def test_merge_preserves_existing_scores_when_graph_is_weaker() -> None:
    original = HybridRetrievalResult(
        chunk_id="chunk_1",
        final_score=0.42,
        keyword_score=1.4,
        symbol_score=0.9,
        file_path="pkg/core.py",
    )

    merged = merge_graph_candidates(
        [original],
        [
            {
                "chunk_id": "chunk_1",
                "graph_score": 0.1,
                "file_path": "pkg/core.py",
                "symbol_name": "run",
            }
        ],
    )

    assert merged[0].final_score == original.final_score
    assert merged[0].keyword_score == original.keyword_score
    assert merged[0].symbol_score == original.symbol_score
    assert original.final_score == 0.42
