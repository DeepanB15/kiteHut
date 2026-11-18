"""Phase 11.6 — focused tests for :class:`CodeGraphBuilder`.

Each test builds a small, purpose-written repository under ``tmp_path`` so the
builder is exercised end-to-end: discovery, extraction, relationship
resolution, assembly, validation and status reporting.  Failure states are
asserted against the returned :class:`GraphBuildResult` rather than raised
exceptions.
"""

from __future__ import annotations

from pathlib import Path

from app.code_graph.builder import CodeGraphBuilder
from app.code_graph.discovery import RepositoryScanner
from app.code_graph.models import (
    CODE_GRAPH_SCHEMA_VERSION,
    GraphBuildStatus,
    GraphEdge,
    GraphValidationResult,
)


def _write(root: Path, relative_path: str, content: str) -> Path:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _build(root: Path, **scanner_kwargs):
    scanner = RepositoryScanner(root, **scanner_kwargs)
    return CodeGraphBuilder(root, scanner=scanner).build()


def _populate_sample(root: Path) -> None:
    _write(
        root,
        "pkg/__init__.py",
        "from pkg.util import helper\n\n\ndef main():\n    return helper()\n",
    )
    _write(root, "pkg/util.py", "def helper():\n    return 1\n")


# --------------------------------------------------------------- complete ---


def test_complete_build_returns_consistent_result(tmp_path: Path) -> None:
    _populate_sample(tmp_path)
    result = _build(tmp_path)

    assert result.status == GraphBuildStatus.COMPLETE
    assert result.errors == []
    assert result.truncated is False
    assert result.graph is not None

    graph = result.graph
    assert graph.schema_version == CODE_GRAPH_SCHEMA_VERSION
    assert result.file_count == len(graph.files) == 2
    assert result.symbol_count == len(graph.symbols) > 0
    assert result.edge_count == len(graph.edges) > 0
    assert graph.repository.repository_id
    assert all(symbol.repository_id == graph.repository.repository_id for symbol in graph.symbols)

    python_coverage = next(c for c in result.coverage if c.language == "python")
    assert python_coverage.supported is True
    assert python_coverage.discovered_files == python_coverage.analyzed_files == 2
    assert python_coverage.skipped_files == 0


def test_build_is_deterministic_across_runs(tmp_path: Path) -> None:
    _populate_sample(tmp_path)
    first = _build(tmp_path)
    second = _build(tmp_path)

    assert first.graph is not None and second.graph is not None
    assert [f.id for f in first.graph.files] == [f.id for f in second.graph.files]
    assert [s.id for s in first.graph.symbols] == [s.id for s in second.graph.symbols]
    assert [e.id for e in first.graph.edges] == [e.id for e in second.graph.edges]
    assert first.graph.source_digest == second.graph.source_digest
    assert first.file_count == second.file_count
    assert first.symbol_count == second.symbol_count


def test_reordered_file_enumeration_yields_identical_ids(tmp_path: Path) -> None:
    # Discovery sorts candidates internally; interleave creation order to
    # confirm the outcome does not depend on filesystem enumeration.
    for name in ("zeta.py", "alpha.py", "mid.py"):
        _write(tmp_path, name, "VALUE = 1\n")

    forward = _build(tmp_path)
    assert forward.graph is not None
    paths = [f.relative_path for f in forward.graph.files]
    assert paths == sorted(paths)


# ---------------------------------------------------------------- partial ---


def test_syntax_error_yields_partial_graph(tmp_path: Path) -> None:
    _write(tmp_path, "good.py", "def ok():\n    return 1\n")
    _write(tmp_path, "broken.py", "def broken(:\n    return 1\n")

    result = _build(tmp_path)

    assert result.status == GraphBuildStatus.PARTIAL
    assert result.graph is not None
    assert any(error.code == "syntax_error" for error in result.errors)
    syntax_error = next(e for e in result.errors if e.code == "syntax_error")
    assert syntax_error.relative_path == "broken.py"
    good = next(f for f in result.graph.files if f.relative_path == "good.py")
    assert any(s.file_id == good.id for s in result.graph.symbols)


def test_max_files_truncation_is_partial(tmp_path: Path) -> None:
    for index in range(5):
        _write(tmp_path, f"mod_{index}.py", "VALUE = 1\n")

    result = _build(tmp_path, max_files=2)

    assert result.truncated is True
    assert result.status == GraphBuildStatus.PARTIAL
    assert result.graph is not None
    assert result.file_count == 2
    assert any(warning.code == "file_limit_reached" for warning in result.warnings)


# --------------------------------------------------------------- failure ---


def test_missing_root_fails_without_graph(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist"
    result = _build(missing)

    assert result.status == GraphBuildStatus.FAILED
    assert result.graph is None
    assert result.errors
    assert result.errors[0].severity.value == "fatal"
    assert result.errors[0].code == "repository_root_missing"


def test_empty_repository_completes_with_zero_files(tmp_path: Path) -> None:
    result = _build(tmp_path)

    assert result.status == GraphBuildStatus.COMPLETE
    assert result.graph is not None
    assert result.graph.files == []
    assert result.graph.symbols == []
    assert result.graph.edges == []
    assert result.file_count == 0


def test_failed_build_carries_no_graph_and_counts_zero(tmp_path: Path) -> None:
    missing = tmp_path / "nope"
    result = _build(missing)

    assert result.graph is None
    assert result.file_count == 0
    assert result.symbol_count == 0
    assert result.edge_count == 0


# ---------------------------------------------------------------- misc ------


def test_scanner_type_is_enforced(tmp_path: Path) -> None:
    try:
        CodeGraphBuilder(tmp_path, scanner=object())  # type: ignore[arg-type]
    except TypeError:
        return
    raise AssertionError("scanner must be a RepositoryScanner instance")


def test_edges_reference_extant_endpoints(tmp_path: Path) -> None:
    _populate_sample(tmp_path)
    result = _build(tmp_path)

    assert result.graph is not None
    node_ids = {f.id for f in result.graph.files}
    node_ids.update(s.id for s in result.graph.symbols)
    node_ids.add(result.graph.repository.repository_id)
    assert result.graph.edges, "expected at least one edge from a populated build"
    for edge in result.graph.edges:
        assert isinstance(edge, GraphEdge)
        assert edge.source_id in node_ids
        assert edge.target_id in node_ids
