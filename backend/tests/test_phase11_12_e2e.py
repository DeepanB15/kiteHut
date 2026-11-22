"""Phase 11.12 — end-to-end Code Graph evaluation.

Exercises the complete pipeline against a realistic, multi-module Python
fixture (``tests/fixtures/code_graph/e2e_project``):

    discovery -> AST extraction -> relationship extraction -> graph building
    -> validation -> smart context retrieval -> evidence verification
    -> agent / MCP execution

Every test copies the committed fixture into ``tmp_path`` first: the fixture
itself is never mutated, and no test starts a server, database or network
service.

Assertions are deliberately source-backed.  The "no incorrect edges" tests
re-parse the files on disk and confirm that every emitted CALLS/IMPORTS edge
corresponds to actual source text, not merely to another graph structure.
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
import shutil
from pathlib import Path
from typing import Any, Dict, Set

import pytest

from app.agent.permissions.manager import PermissionManager
from app.agent.router.router import AgentRouter
from app.agent.router.tool_executor import ToolExecutor
from app.agent.state.agent_state import AgentTask
from app.chunking.repository_chunker import chunk_repo
from app.code_graph import (
    CODE_GRAPH_SCHEMA_VERSION,
    CodeGraphBuilder,
    GraphBuildStatus,
    deserialize_graph_json,
    find_symbols,
    serialize_graph_json,
)
from app.code_graph.evidence import collect_graph_evidence, verify_claim_with_graph
from app.code_graph.integration import (
    _align_candidates_to_chunks,
    integrate_graph_into_retrieval,
)
from app.code_graph.models import EdgeKind, ResolutionKind, SymbolKind
from app.mcp.server import RepoLensMCPServer
from app.retrieval.hybrid.retrieval import HybridRetriever
from app.tools.registry import create_default_tool_registry
from app.verification.models.claim import ClaimType, ExtractedClaim

FIXTURE_PROJECT = Path(__file__).parent / "fixtures" / "code_graph" / "e2e_project"
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


# ---------------------------------------------------------------------------
# Fixtures and small helpers
# ---------------------------------------------------------------------------


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "e2e_project"
    shutil.copytree(FIXTURE_PROJECT, root)
    return root


@pytest.fixture()
def built(repo: Path):
    result = CodeGraphBuilder(repo).build()
    assert result.graph is not None, result.errors
    return repo, result


def _read_text(root: Path, relative_path: str) -> str:
    return (root / relative_path).read_text(encoding="utf-8")


def _symbols_by_qn(graph) -> Dict[str, Any]:
    return {symbol.qualified_name: symbol for symbol in graph.symbols}


def _dotted_module(relative_path: str) -> str:
    stem = relative_path[:-3] if relative_path.endswith(".py") else relative_path
    if stem.lower().endswith("__init__"):
        stem = stem[: -len("__init__")]
    stem = stem.strip("/")
    if not stem:
        return "."
    return stem.replace("/", ".")


def _declared_names_at(root: Path, relative_path: str, line: int) -> Set[str]:
    """Names declared by a def/class node starting at ``line``."""
    tree = ast.parse(_read_text(root, relative_path))
    names: Set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(
            node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
        ):
            continue
        first_line = node.lineno
        decorators = getattr(node, "decorator_list", None)
        if decorators:
            first_line = decorators[0].lineno
        if first_line == line:
            names.add(node.name)
    return names


def _import_targets(root: Path, relative_path: str) -> Set[str]:
    """Every dotted module a source file's absolute imports can address."""
    tree = ast.parse(_read_text(root, relative_path))
    targets: Set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                targets.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            module = node.module or ""
            if module:
                targets.add(module)
            for alias in node.names:
                if alias.name != "*":
                    targets.add(f"{module}.{alias.name}".strip("."))
    return targets


def _invoke(
    name: str,
    args: Dict[str, Any],
    repository_path: Path,
    permissions: PermissionManager | None = None,
) -> Dict[str, Any]:
    registry = create_default_tool_registry()
    result = registry.execute(
        tool_name=name,
        arguments=args,
        repository_path=str(repository_path),
        permission_manager=permissions or PermissionManager(auto_allow_safe=True),
        task_id="phase11_12_e2e",
    )
    assert result.success, result.error
    return json.loads(result.output)


def _claim(**overrides: Any) -> ExtractedClaim:
    payload: Dict[str, Any] = {
        "claim_id": "phase11_12_claim",
        "claim_type": ClaimType.GENERIC,
        "statement": "the fixture implementation matches the claim",
    }
    payload.update(overrides)
    return ExtractedClaim(**payload)


# ---------------------------------------------------------------------------
# 1. Full pipeline: multi-module repository
# ---------------------------------------------------------------------------


def test_full_pipeline_builds_multimodule_graph(built) -> None:
    repo, result = built
    graph = result.graph

    # A syntax error in one fixture module yields a partial, still-usable graph.
    assert result.status == GraphBuildStatus.PARTIAL
    assert result.truncated is False
    assert result.file_count == 14
    assert result.symbol_count >= 40
    assert result.edge_count > 0

    files = {file.relative_path for file in graph.files}
    assert {
        "__init__.py",
        "app/__init__.py",
        "app/util.py",
        "app/models.py",
        "app/service.py",
        "app/main.py",
        "app/empty_module.py",
        "app/unicode_module.py",
        "pkg_a/helper.py",
        "pkg_b/helper.py",
        "pkg_b/consumer.py",
    } <= files

    kinds = {edge.kind for edge in graph.edges}
    assert {
        EdgeKind.CONTAINS,
        EdgeKind.DEFINES,
        EdgeKind.IMPORTS,
        EdgeKind.CALLS,
    } <= kinds

    # The builder only emits resolved edges; ambiguous/unresolved
    # relationships stay diagnostics.
    assert all(edge.resolution == ResolutionKind.RESOLVED for edge in graph.edges)

    # Validation ran as part of the build and rejected nothing.
    assert graph.schema_version == CODE_GRAPH_SCHEMA_VERSION
    assert result.errors and all(
        error.code in {"syntax_error"} for error in result.errors
    )


def test_no_incorrect_calls_or_imports_edges(built) -> None:
    """Every CALLS/IMPORTS edge must correspond to real source text."""
    repo, result = built
    graph = result.graph
    symbols = {symbol.id: symbol for symbol in graph.symbols}
    files = {file.id: file for file in graph.files}

    call_edges = [e for e in graph.edges if e.kind == EdgeKind.IMPORTS]
    assert call_edges, "fixture must exercise IMPORTS"

    for edge in call_edges:
        source = files[edge.source_id]
        target = files[edge.target_id]
        assert edge.source_file == source.relative_path
        assert _dotted_module(target.relative_path) in _import_targets(
            repo, source.relative_path
        ), f"IMPORTS edge is not backed by source: {source.relative_path} -> {target.relative_path}"

    calls = [e for e in graph.edges if e.kind == EdgeKind.CALLS]
    assert calls, "fixture must exercise CALLS"
    for edge in calls:
        caller = symbols[edge.source_id]
        callee = symbols[edge.target_id]
        # CALLS edges are symbol-to-symbol within the same file.
        assert caller.relative_path == edge.source_file
        assert callee.relative_path == edge.source_file
        line = _read_text(repo, edge.source_file).splitlines()[edge.start_line - 1]
        callee_name = edge.metadata["callee"]
        assert callee_name in line and "(" in line
        assert callee_name in _declared_names_at(
            repo, callee.relative_path, callee.start_line
        ), f"CALLS target is not declared at its recorded span: {edge.id}"


# ---------------------------------------------------------------------------
# 2-3. Nested scopes, imports and calls
# ---------------------------------------------------------------------------


def test_nested_classes_functions_and_lexical_parents(built) -> None:
    _, result = built
    graph = result.graph
    by_qn = _symbols_by_qn(graph)
    by_id = {symbol.id: symbol for symbol in graph.symbols}

    assert by_qn["app/models.Record.Meta"].kind == SymbolKind.CLASS
    assert by_qn["app/models.Record.Meta.describe"].kind == SymbolKind.METHOD
    assert by_qn["app/service.nested_computation.step_one"].kind == SymbolKind.FUNCTION
    assert (
        by_qn["app/service.Service.process.normalize"].kind == SymbolKind.FUNCTION
    )

    # parent_id now reflects the lexical hierarchy at every depth.
    assert by_id[by_qn["app/models.Record.Meta"].parent_id].qualified_name == (
        "app/models.Record"
    )
    assert by_id[
        by_qn["app/models.Record.Meta.describe"].parent_id
    ].qualified_name == ("app/models.Record.Meta")
    assert by_id[
        by_qn["app/service.nested_computation.step_one"].parent_id
    ].qualified_name == ("app/service.nested_computation")
    assert by_id[
        by_qn["app/service.nested_computation.step_two"].parent_id
    ].qualified_name == ("app/service.nested_computation")
    # Top-level declarations are owned by their module symbol.
    assert by_id[by_qn["app/service.build_registry"].parent_id].kind == (
        SymbolKind.MODULE
    )


def test_imports_and_resolved_calls_are_emitted(built) -> None:
    _, result = built
    graph = result.graph
    by_qn = _symbols_by_qn(graph)

    import_edges = {
        (edge.source_file, graph_file.relative_path)
        for edge in graph.edges
        if edge.kind == EdgeKind.IMPORTS
        for graph_file in graph.files
        if graph_file.id == edge.target_id
    }
    assert ("app/main.py", "app/service.py") in import_edges
    assert ("app/main.py", "app/models.py") in import_edges
    assert ("app/service.py", "app/util.py") in import_edges
    assert ("app/service.py", "app/models.py") in import_edges
    assert ("pkg_b/consumer.py", "pkg_a/helper.py") in import_edges
    assert ("pkg_b/consumer.py", "pkg_b/helper.py") in import_edges

    call_edges = {
        (edge.source_id, edge.target_id)
        for edge in graph.edges
        if edge.kind == EdgeKind.CALLS
    }
    # Unique same-module calls resolve, including Unicode identifiers.
    assert (
        by_qn["app/util.helper"].id,
        by_qn["app/util.slugify"].id,
    ) in call_edges
    assert (
        by_qn["app/unicode_module.résumé"].id,
        by_qn["app/unicode_module.saluda"].id,
    ) in call_edges
    assert (
        by_qn["app/main"].id,
        by_qn["app/main.main"].id,
    ) in call_edges

    # Imports are file-to-file, never file-to-symbol.
    symbol_ids = set(by_qn[symbol].id for symbol in by_qn)
    for edge in graph.edges:
        if edge.kind == EdgeKind.IMPORTS:
            assert edge.target_id not in symbol_ids


# ---------------------------------------------------------------------------
# 4-5. Duplicate, ambiguous, shadowed and unresolved symbols
# ---------------------------------------------------------------------------


def test_duplicate_symbols_are_never_guessed(built) -> None:
    repo, result = built
    graph = result.graph

    duplicates = [s for s in graph.symbols if s.name == "duplicate"]
    assert len(duplicates) == 2
    assert len({s.id for s in duplicates}) == 2
    assert {s.qualified_name for s in duplicates} == {"app/service.duplicate"}
    assert {s.occurrence_ordinal for s in duplicates} == {0, 1}

    # Public query layer and the agent tool both report ambiguity.
    assert len(find_symbols(graph, "duplicate")) == 2
    payload = _invoke("graph_find_symbol", {"query": "duplicate"}, repo)
    assert payload["ambiguous"] is True
    assert payload["count"] == 2

    callers_payload = _invoke("graph_callers", {"symbol": "duplicate"}, repo)
    assert callers_payload["ambiguous"] is True
    assert callers_payload["relationships"] == []
    assert len(callers_payload["candidates"]) == 2

    # The duplicate call site resolves to neither declaration.
    calls_duplicate = next(
        s.qualified_name for s in graph.symbols if s.name == "calls_duplicate"
    )
    calls_duplicate_id = next(
        s.id for s in graph.symbols if s.qualified_name == calls_duplicate
    )
    target_ids = {s.id for s in duplicates}
    assert not [
        edge
        for edge in graph.edges
        if edge.kind == EdgeKind.CALLS
        and edge.source_id == calls_duplicate_id
        and edge.target_id in target_ids
    ]
    assert any(
        diagnostic.code == "call_ambiguous_declarations"
        for diagnostic in result.unresolved_calls
    )

    # The same bare name in three modules is also ambiguous for lookup.
    helper_matches = find_symbols(graph, "helper")
    assert len(helper_matches) == 3
    helper_payload = _invoke("graph_find_symbol", {"query": "helper"}, repo)
    assert helper_payload["ambiguous"] is True
    # A qualified name still resolves uniquely.
    qualified_payload = _invoke(
        "graph_find_symbol", {"query": "pkg_a/helper.helper"}, repo
    )
    assert qualified_payload["ambiguous"] is False
    assert qualified_payload["count"] == 1


def test_shadowed_and_unresolved_calls_emit_diagnostics_only(built) -> None:
    _, result = built
    graph = result.graph

    codes = {diagnostic.code for diagnostic in result.unresolved_calls}
    assert "call_shadowed_unresolved" in codes
    assert "call_unresolved_no_target" in codes
    assert "attribute_call_unresolved" in codes

    shadowed = [
        d
        for d in result.unresolved_calls
        if d.code == "call_shadowed_unresolved"
        and d.relative_path == "app/service.py"
        and d.line == 29
    ]
    assert len(shadowed) == 1
    assert "helper" in shadowed[0].message

    unresolved = [
        d
        for d in result.unresolved_calls
        if d.code == "call_unresolved_no_target"
        and d.relative_path == "app/service.py"
        and d.line == 34
    ]
    assert len(unresolved) == 1

    # No CALLS edge may claim any of these unresolved targets were resolved.
    shadowed_symbol = next(
        s for s in graph.symbols if s.qualified_name == "app/service.shadowed"
    )
    assert not [
        edge
        for edge in graph.edges
        if edge.kind == EdgeKind.CALLS and edge.source_id == shadowed_symbol.id
    ]
    no_target_symbol = next(
        s for s in graph.symbols if s.qualified_name == "app/service.unresolved"
    )
    assert not [
        edge
        for edge in graph.edges
        if edge.kind == EdgeKind.CALLS and edge.source_id == no_target_symbol.id
    ]
    # Attribute calls (self.describe) are never converted to CALLS edges.
    call_method = next(
        s
        for s in graph.symbols
        if s.qualified_name == "app/service.Service.call_method"
    )
    assert not [
        edge
        for edge in graph.edges
        if edge.kind == EdgeKind.CALLS and edge.source_id == call_method.id
    ]


# ---------------------------------------------------------------------------
# 6-7. Syntax errors, empty files and Unicode
# ---------------------------------------------------------------------------


def test_syntax_error_yields_partial_build_with_diagnostics(built) -> None:
    _, result = built
    graph = result.graph

    assert result.status == GraphBuildStatus.PARTIAL
    syntax_errors = [e for e in result.errors if e.code == "syntax_error"]
    assert len(syntax_errors) == 1
    error = syntax_errors[0]
    assert error.relative_path == "app/legacy_broken.py"
    assert error.line == 4
    assert error.message.count("app/legacy_broken.py") == 1
    assert "invalid syntax" in error.message

    # The broken file is discovered but contributes no fabricated symbols.
    assert "app/legacy_broken.py" in {f.relative_path for f in graph.files}
    assert not [
        symbol
        for symbol in graph.symbols
        if symbol.relative_path == "app/legacy_broken.py"
    ]

    python_coverage = next(
        entry for entry in result.coverage if entry.language == "python"
    )
    assert python_coverage.discovered_files == 14
    assert python_coverage.analyzed_files == 13
    assert python_coverage.skipped_files == 1

    # The rest of the repository is still available to the agent.
    assert any(
        symbol.qualified_name == "app/main.main" for symbol in graph.symbols
    )


def test_empty_and_unicode_sources_round_trip(built) -> None:
    repo, result = built
    graph = result.graph

    empty_symbols = [
        symbol
        for symbol in graph.symbols
        if symbol.relative_path == "app/empty_module.py"
    ]
    assert len(empty_symbols) == 1
    assert empty_symbols[0].kind == SymbolKind.MODULE
    assert empty_symbols[0].start_line == 1
    assert empty_symbols[0].end_line == 1

    unicode_symbol = next(
        symbol
        for symbol in graph.symbols
        if symbol.relative_path == "app/unicode_module.py"
        and symbol.kind == SymbolKind.FUNCTION
        and symbol.name == "résumé"
    )
    assert unicode_symbol.qualified_name == "app/unicode_module.résumé"

    # Unicode identifiers and multibyte source survive canonical serialization.
    serialized = serialize_graph_json(graph)
    restored, validation = deserialize_graph_json(serialized)
    assert validation.valid is True
    assert restored is not None
    assert any(symbol.name == "résumé" for symbol in restored.symbols)
    assert serialize_graph_json(restored) == serialized

    unicode_file = next(
        f for f in graph.files if f.relative_path == "app/unicode_module.py"
    )
    raw = (repo / "app" / "unicode_module.py").read_bytes()
    assert unicode_file.content_hash == hashlib.sha256(raw).hexdigest()


# ---------------------------------------------------------------------------
# 8-9. Evidence verification
# ---------------------------------------------------------------------------


def test_fresh_evidence_supports_and_stale_evidence_cannot(built) -> None:
    repo, result = built
    graph = result.graph
    claim = _claim(
        claim_id="stale_check",
        statement="main calls build_registry",
        target_file="app/main.py",
        target_line=11,
        expected_pattern="registry = build_registry()",
    )

    fresh = verify_claim_with_graph(claim, repo, graph=graph)
    assert fresh.status.value == "SUPPORTED"
    assert fresh.bundle.diagnostics["stale_count"] == 0

    # Mutate the file after the graph snapshot was taken.
    main_file = repo / "app" / "main.py"
    main_file.write_text(
        main_file.read_text(encoding="utf-8") + "\n# drift after snapshot\n",
        encoding="utf-8",
    )

    stale = verify_claim_with_graph(claim, repo, graph=graph)
    assert stale.status.value == "INCONCLUSIVE"
    assert stale.bundle.diagnostics["stale_count"] >= 1
    stale_spans = [
        span
        for span in stale.bundle.spans
        if span.relative_path == "app/main.py" and span.claim_relevant
    ]
    assert stale_spans
    assert all(span.stale for span in stale_spans)
    assert all(
        span.stale_reason == "source_hash_mismatch" for span in stale_spans
    )
    assert stale.bundle.diagnostics["evidence_count"] == 0
    assert all(
        "stale" in reason.lower() for reason in stale.reasons
    )


def test_missing_evidence_is_not_contradictory_evidence(built) -> None:
    repo, result = built
    graph = result.graph

    # Direct observation of absence refutes an existence claim.
    missing_file = verify_claim_with_graph(
        _claim(
            claim_id="missing_file",
            claim_type=ClaimType.FILE_EXISTS,
            statement="app/nope.py exists",
            target_file="app/nope.py",
        ),
        repo,
        graph=graph,
    )
    assert missing_file.status.value == "UNSUPPORTED"
    assert missing_file.verdict.status.value == "FALSE"

    # The same absence for a content claim is insufficient, not contradictory.
    missing_content = verify_claim_with_graph(
        _claim(
            claim_id="missing_content",
            statement="app/nope.py contains whatever()",
            target_file="app/nope.py",
            expected_pattern="whatever()",
        ),
        repo,
        graph=graph,
    )
    assert missing_content.status.value == "INCONCLUSIVE"
    assert missing_content.verdict.status.value == "FALSE"

    # Missing evidence for a claim with no locations never yields SUPPORTED.
    no_locations = verify_claim_with_graph(
        _claim(
            claim_id="no_locations",
            statement="the architecture is layered",
        ),
        repo,
        graph=graph,
    )
    assert no_locations.status.value == "INCONCLUSIVE"


def test_ambiguous_symbols_cannot_support_a_claim(built) -> None:
    repo, result = built
    graph = result.graph

    ambiguous = verify_claim_with_graph(
        _claim(
            claim_id="ambiguous",
            statement="duplicate returns the first value",
        ),
        repo,
        graph=graph,
    )
    assert ambiguous.status.value == "INCONCLUSIVE"
    assert ambiguous.bundle.diagnostics["ambiguous_count"] >= 1
    assert ambiguous.bundle.diagnostics["supporting_count"] == 0

    # Even an asserted pattern that literally exists in one of two duplicate
    # declarations must not resolve the ambiguity by picking one of them.
    ambiguous_pattern = verify_claim_with_graph(
        _claim(
            claim_id="ambiguous_pattern",
            statement="duplicate returns the first value",
            expected_pattern='return "first"',
        ),
        repo,
        graph=graph,
    )
    assert ambiguous_pattern.status.value == "INCONCLUSIVE"
    named_spans = [
        span
        for span in ambiguous_pattern.bundle.spans
        if span.relationship == "named_symbol"
    ]
    assert len(named_spans) == 2
    assert all(span.ambiguous for span in named_spans)

    # Even if the statement asserts no exact pattern, graph-only navigation
    # must never be promoted to support.
    navigation_only = verify_claim_with_graph(
        _claim(
            claim_id="navigation",
            statement="calls_duplicate calls duplicate",
        ),
        repo,
        graph=graph,
    )
    assert navigation_only.status.value != "SUPPORTED"


def test_claim_with_exact_source_pattern_is_supported(built) -> None:
    repo, result = built
    graph = result.graph

    supported = verify_claim_with_graph(
        _claim(
            claim_id="supported",
            statement="nested_computation returns step_two(value)",
            target_file="app/service.py",
            target_line=24,
            expected_pattern="return step_two(value)",
        ),
        repo,
        graph=graph,
    )
    assert supported.status.value == "SUPPORTED"
    assert supported.verdict.status.value == "TRUE"
    assert any(
        span.relationship == "claim_target" and span.exact_match
        for span in supported.bundle.spans
    )
    # Navigation evidence is recorded but never submitted as proof.
    assert supported.bundle.diagnostics["navigation_only_count"] >= 1
    assert all(
        "graph_navigation_only" in item.metadata
        for item in supported.bundle.evidence_items
    )


# ---------------------------------------------------------------------------
# 10-11. Repository boundaries and workspace enforcement
# ---------------------------------------------------------------------------


def test_repository_boundaries_are_enforced(repo: Path) -> None:
    registry = create_default_tool_registry()
    outside = repo.parent / "outside.py"
    outside.write_text("def outside():\n    return 1\n", encoding="utf-8")

    traversal = registry.execute(
        "graph_imports",
        {"path": "../../outside.py"},
        repository_path=str(repo),
        permission_manager=PermissionManager(auto_allow_safe=True),
    )
    assert traversal.success is False
    assert "traversal" in (traversal.error or "").lower()

    absolute = registry.execute(
        "graph_imports",
        {"path": str(outside)},
        repository_path=str(repo),
        permission_manager=PermissionManager(auto_allow_safe=True),
    )
    assert absolute.success is False
    assert "outside repository" in (absolute.error or "").lower()

    claim = registry.execute(
        "verify_claim",
        {
            "claim": "outside exists",
            "claim_type": "FILE_EXISTS",
            "target_file": str(outside),
        },
        repository_path=str(repo),
        permission_manager=PermissionManager(auto_allow_safe=True),
    )
    assert claim.success is False
    assert "outside repository" in (claim.error or "").lower()

    # The evidence collector itself drops unsafe claim paths rather than
    # reading them, even when called outside the tool layer.
    bundle = collect_graph_evidence(
        _claim(
            claim_id="escape",
            statement="outside exists",
            target_file="../outside.py",
            expected_pattern="def outside",
        ),
        repo,
    )
    assert bundle.spans == []

    # The full verification entry point must not hand an unsafe target to the
    # pre-existing collector either: no outside evidence may be read.
    for unsafe_target in ("../outside.py", str(outside)):
        outcome = verify_claim_with_graph(
            _claim(
                claim_id="direct_escape",
                statement="outside exists",
                target_file=unsafe_target,
                expected_pattern="def outside",
            ),
            repo,
        )
        assert outcome.bundle.diagnostics["claim_target_within_repository"] is False
        assert outcome.status.value == "INCONCLUSIVE"
        assert outcome.verdict.evidence_ids == []
        assert all(
            not (item.source_file or "").endswith("outside.py")
            for item in outcome.bundle.evidence_items
        )


def test_symlink_escaping_repository_is_not_discovered(repo: Path) -> None:
    outside = repo.parent / "outside_symbols.py"
    outside.write_text("def escaped_symbol():\n    return 1\n", encoding="utf-8")
    link = repo / "escape.py"
    try:
        os.symlink(outside, link)
    except (OSError, NotImplementedError) as error:  # pragma: no cover
        pytest.skip(f"Symlinks are not available in this environment: {error}")

    result = CodeGraphBuilder(repo).build()
    assert result.graph is not None
    assert "escape.py" not in {f.relative_path for f in result.graph.files}
    assert not [
        symbol
        for symbol in result.graph.symbols
        if symbol.name == "escaped_symbol"
    ]
    assert any(
        warning.code == "symlink_outside_root" for warning in result.warnings
    )


def test_mcp_and_registry_cannot_widen_the_workspace(tmp_path: Path) -> None:
    server_root = tmp_path / "server_root"
    other_root = tmp_path / "other_root"
    shutil.copytree(FIXTURE_PROJECT, server_root)
    shutil.copytree(FIXTURE_PROJECT, other_root)
    (other_root / "app" / "only_elsewhere.py").write_text(
        "def only_elsewhere():\n    return 1\n", encoding="utf-8"
    )

    # Registry: the trusted execution workspace always wins.
    registry = create_default_tool_registry()
    overridden = registry.execute(
        "graph_find_symbol",
        {"query": "main", "repository_path": str(other_root)},
        repository_path=str(server_root),
        permission_manager=PermissionManager(auto_allow_safe=True),
    )
    assert overridden.success is True
    payload = json.loads(overridden.output)
    assert payload["count"] == 1
    assert payload["matches"][0]["relative_path"] == "app/main.py"

    # MCP: the server pins its own repository for every wrapped tool.
    server = RepoLensMCPServer(repository_path=str(server_root))
    assert GRAPH_TOOL_NAMES <= set(server.get_registered_tool_names())
    wrapper = server._wrap_tool(server.registry.get("graph_find_symbol"))
    response = wrapper(query="only_elsewhere", repository_path=str(other_root))
    assert response["success"] is True
    assert response["data"]["count"] == 0


# ---------------------------------------------------------------------------
# 12. Deterministic graph serialization
# ---------------------------------------------------------------------------


def test_repeated_builds_are_deterministic(repo: Path) -> None:
    first = CodeGraphBuilder(repo).build()
    second = CodeGraphBuilder(repo).build()
    assert first.graph is not None and second.graph is not None

    first_json = serialize_graph_json(first.graph)
    second_json = serialize_graph_json(second.graph)
    assert first_json == second_json
    assert first.edge_count == second.edge_count
    assert first.symbol_count == second.symbol_count
    assert first.status == second.status

    edge_ids = [edge.id for edge in first.graph.edges]
    assert edge_ids == sorted(edge_ids)
    assert len(edge_ids) == len(set(edge_ids))
    symbol_ids = [symbol.id for symbol in first.graph.symbols]
    assert len(symbol_ids) == len(set(symbol_ids))

    restored, validation = deserialize_graph_json(first_json)
    assert validation.valid is True
    assert restored is not None
    assert serialize_graph_json(restored) == first_json


# ---------------------------------------------------------------------------
# Smart context retrieval
# ---------------------------------------------------------------------------


def test_smart_context_preserves_existing_retrieval(built) -> None:
    repo, result = built
    graph = result.graph
    chunks = [chunk for chunk_list in chunk_repo(str(repo)) for chunk in chunk_list.chunks]
    assert chunks

    baseline_by_query = {
        query: HybridRetriever(chunks=chunks).retrieve(query=query, top_k=20)
        for query in ("helper", "duplicate", "main")
    }
    assert baseline_by_query["helper"]

    for query, baseline in baseline_by_query.items():
        baseline_ids = {candidate.chunk_id for candidate in baseline}
        merged, diagnostics = integrate_graph_into_retrieval(
            query, graph, chunks
        )
        merged_ids = {candidate.chunk_id for candidate in merged}
        # Existing retrieval results are never removed or down-scored.
        assert baseline_ids <= merged_ids
        assert diagnostics["graph_valid"] is True
        assert diagnostics["fallback_used"] is False
        assert diagnostics["retrieval_candidates_after_merge"] >= (
            diagnostics["retrieval_candidates_before_merge"]
        )
        baseline_by_id = {candidate.chunk_id: candidate for candidate in baseline}
        for candidate in merged:
            previous = baseline_by_id.get(candidate.chunk_id)
            if previous is not None:
                assert candidate.keyword_score == previous.keyword_score
                assert candidate.semantic_score == previous.semantic_score
                assert candidate.final_score >= previous.final_score - 1e-12

    # graph=None reproduces the existing retriever exactly.
    fallback, fallback_diagnostics = integrate_graph_into_retrieval(
        "helper", None, chunks
    )
    assert fallback_diagnostics["fallback_used"] is True
    assert [(c.chunk_id, c.final_score) for c in fallback] == [
        (c.chunk_id, c.final_score) for c in baseline_by_query["helper"]
    ]


def test_ambiguous_chunk_alignment_never_selects_arbitrarily(built) -> None:
    repo, result = built
    graph = result.graph
    chunks = [chunk for chunk_list in chunk_repo(str(repo)) for chunk in chunk_list.chunks]
    chunks_by_id = {chunk.chunk_id: chunk for chunk in chunks}

    from app.code_graph.integration import discover_graph_candidates

    candidates = discover_graph_candidates("duplicate", graph)
    duplicate_candidates = [
        candidate
        for candidate in candidates
        if candidate.get("symbol_name") == "duplicate"
    ]
    assert len(duplicate_candidates) == 2

    aligned = _align_candidates_to_chunks(candidates, chunks)
    aligned_duplicates = [
        candidate
        for candidate in aligned
        if candidate.get("symbol_name") == "duplicate"
    ]
    assert len(aligned_duplicates) == 2
    # Exact spans disambiguate the two same-name symbols.
    assert len({candidate["chunk_id"] for candidate in aligned_duplicates}) == 2
    for candidate in aligned_duplicates:
        chunk = chunks_by_id[candidate["chunk_id"]]
        assert chunk.file_path == candidate["file_path"]
        assert chunk.start_line == candidate["start_line"]
        assert chunk.end_line == candidate["end_line"]


# ---------------------------------------------------------------------------
# Agent / MCP execution
# ---------------------------------------------------------------------------


def test_agent_executes_graph_tool_through_existing_boundary(repo: Path) -> None:
    router = AgentRouter()
    executor = ToolExecutor()
    task = AgentTask(
        task_id="phase11_12_route",
        query="Who calls slugify?",
        task_type="QUESTION",
        repository_path=str(repo),
    )

    selection = router.route(task)
    assert selection.primary_tool.tool_name == "graph_callers"

    result = executor.execute_read_only(
        selection, repository_path=str(repo), task_id=task.task_id
    )
    assert result.success is True, result.error
    payload = json.loads(result.output)
    assert payload["symbol_found"] is True
    caller_names = {
        entry["node"]["name"] for entry in payload["relationships"]
    }
    assert "helper" in caller_names
    assert payload["navigation_only"] is True


def test_mcp_end_to_end_verifies_a_claim(repo: Path) -> None:
    server = RepoLensMCPServer(repository_path=str(repo))
    wrapper = server._wrap_tool(server.registry.get("verify_claim"))

    response = wrapper(
        claim="nested_computation returns step_two(value)",
        claim_type="GENERIC",
        target_file="app/service.py",
        target_line=24,
        expected_pattern="return step_two(value)",
    )

    assert response["success"] is True
    assert response["data"]["status"] == "SUPPORTED"
    assert response["data"]["verdict"]["status"] == "TRUE"

    stale_response = wrapper(
        claim="app/nope.py exists",
        claim_type="FILE_EXISTS",
        target_file="app/nope.py",
    )
    assert stale_response["success"] is True
    assert stale_response["data"]["status"] == "UNSUPPORTED"
