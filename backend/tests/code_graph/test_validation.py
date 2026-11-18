"""Phase 11.5 — focused tests for the deterministic validation layer.

The CodeGraph models enforce most invariants at construction time, so the
tests mutate fields in place on otherwise-valid graphs to exercise the
validation pass.  Model assignment is not validated, which keeps the
"cannot even build this" cases inside the model tests.
"""

import pytest

from app.code_graph import GraphEdge, GraphValidationResult
from app.code_graph.models import (
    CodeGraph,
    DiagnosticSeverity,
    EdgeKind,
    FileNode,
    GraphDiagnostic,
    ProvenanceKind,
    RepositoryNode,
    SymbolKind,
    SymbolNode,
    sha256_hex,
)
from app.code_graph.validation import (
    validate_graph,
)

FILE1_CONTENT = "def run():\n    return 1\n"
FILE2_CONTENT = "def helper():\n    return 2\n"
FILE1_HASH = sha256_hex(FILE1_CONTENT)
FILE2_HASH = sha256_hex(FILE2_CONTENT)
SOURCE_DIGEST = sha256_hex("source digest")


def make_repository(repository_id: str = "test-repo") -> RepositoryNode:
    return RepositoryNode(
        repository_id=repository_id,
        name="KiteHut",
        root_path="C:\\repos\\KiteHut",
        source_digest=SOURCE_DIGEST,
    )


def make_file(
    repository: RepositoryNode,
    relative_path: str = "src/app.py",
    content_hash: str = FILE1_HASH,
    line_count: int = 2,
) -> FileNode:
    return FileNode(
        repository_id=repository.repository_id,
        relative_path=relative_path,
        language="python",
        content_hash=content_hash,
        line_count=line_count,
        byte_size=len(content_hash),
    )


def make_symbol(
    file: FileNode,
    name: str = "run",
    qualified_name: str = "src.app.run",
    kind: SymbolKind = SymbolKind.FUNCTION,
    start_line: int = 1,
    end_line: int = 2,
    occurrence_ordinal: int = 0,
) -> SymbolNode:
    return SymbolNode(
        repository_id=file.repository_id,
        file_id=file.id,
        relative_path=file.relative_path,
        name=name,
        qualified_name=qualified_name,
        kind=kind,
        start_line=start_line,
        end_line=end_line,
        start_column=1,
        end_column=12,
        source_hash=file.content_hash,
        occurrence_ordinal=occurrence_ordinal,
    )


def make_repository_contains_edge(
    repository: RepositoryNode, file: FileNode
) -> GraphEdge:
    return GraphEdge(
        repository_id=repository.repository_id,
        source_id=repository.repository_id,
        target_id=file.id,
        kind=EdgeKind.CONTAINS,
        provenance_kind=ProvenanceKind.DISCOVERED_PATH,
        source_file=file.relative_path,
        source_hash=file.content_hash,
    )


def make_defines_edge(file: FileNode, symbol: SymbolNode) -> GraphEdge:
    return GraphEdge(
        repository_id=file.repository_id,
        source_id=file.id,
        target_id=symbol.id,
        kind=EdgeKind.DEFINES,
        provenance_kind=ProvenanceKind.DECLARATION,
        source_file=file.relative_path,
        start_line=symbol.start_line,
        end_line=symbol.end_line,
        source_hash=file.content_hash,
    )


def make_contains_edge(parent: SymbolNode, child: SymbolNode) -> GraphEdge:
    return GraphEdge(
        repository_id=child.repository_id,
        source_id=parent.id,
        target_id=child.id,
        kind=EdgeKind.CONTAINS,
        provenance_kind=ProvenanceKind.DECLARATION,
        source_file=child.relative_path,
        start_line=child.start_line,
        end_line=child.end_line,
        source_hash=child.source_hash,
    )


def make_imports_edge(source: FileNode, target: FileNode) -> GraphEdge:
    return GraphEdge(
        repository_id=source.repository_id,
        source_id=source.id,
        target_id=target.id,
        kind=EdgeKind.IMPORTS,
        provenance_kind=ProvenanceKind.IMPORT_STATEMENT,
        source_file=source.relative_path,
        start_line=1,
        end_line=1,
        start_column=1,
        end_column=12,
        source_hash=source.content_hash,
    )


def make_calls_edge(caller: SymbolNode, callee: SymbolNode) -> GraphEdge:
    return GraphEdge(
        repository_id=caller.repository_id,
        source_id=caller.id,
        target_id=callee.id,
        kind=EdgeKind.CALLS,
        provenance_kind=ProvenanceKind.CALL_SITE,
        source_file=caller.relative_path,
        start_line=2,
        end_line=2,
        start_column=4,
        end_column=15,
        source_hash=caller.source_hash,
    )


def make_valid_graph() -> CodeGraph:
    repository = make_repository()
    first = make_file(repository, "src/app.py", FILE1_HASH)
    second = make_file(repository, "src/util.py", FILE2_HASH)
    first_symbol = make_symbol(first, "run", "src.app.run")
    second_symbol = make_symbol(second, "helper", "src.util.helper")

    return CodeGraph(
        repository=repository,
        files=[first, second],
        symbols=[first_symbol, second_symbol],
        edges=[
            make_repository_contains_edge(repository, first),
            make_repository_contains_edge(repository, second),
            make_defines_edge(first, first_symbol),
            make_defines_edge(second, second_symbol),
            make_imports_edge(first, second),
            make_calls_edge(first_symbol, second_symbol),
        ],
    )


def codes(result: GraphValidationResult):
    return [diagnostic.code for diagnostic in result.errors + result.warnings]


# ---------------------------------------------------------------------------
# Acceptance
# ---------------------------------------------------------------------------


def test_valid_graph_accepted():
    graph = make_valid_graph()
    result = validate_graph(graph)
    assert result.valid is True
    assert result.errors == []
    assert result.warnings == []
    assert result.checked_nodes == 5
    assert result.checked_edges == 6


def test_empty_graph_accepted():
    graph = CodeGraph(repository=make_repository())
    result = validate_graph(graph)
    assert result.valid is True
    assert result.checked_nodes == 1
    assert result.checked_edges == 0


def test_partial_graph_accepted():
    """A graph missing edges (but holding valid entities) still validates."""
    repository = make_repository()
    file = make_file(repository, "src/app.py", FILE1_HASH)
    symbol = make_symbol(file)
    graph = CodeGraph(repository=repository, files=[file], symbols=[symbol])
    result = validate_graph(graph)
    assert result.valid is True
    assert result.checked_nodes == 3


# ---------------------------------------------------------------------------
# Identity uniqueness
# ---------------------------------------------------------------------------


def test_duplicate_node_ids_detected():
    graph = make_valid_graph()
    files = graph.files
    files[1].id = files[0].id  # bypass model assignment validation
    result = validate_graph(graph)
    assert result.valid is False
    assert "duplicate_node_id" in codes(result)


def test_duplicate_edge_ids_detected():
    graph = make_valid_graph()
    source = graph.edges[0]
    graph.edges[1].id = source.id
    result = validate_graph(graph)
    assert result.valid is False
    assert "duplicate_edge_id" in codes(result)


def test_duplicate_symbol_ids_detected():
    graph = make_valid_graph()
    graph.symbols[1].id = graph.symbols[0].id
    result = validate_graph(graph)
    assert result.valid is False
    assert "duplicate_node_id" in codes(result)


# ---------------------------------------------------------------------------
# Endpoints and repository ownership
# ---------------------------------------------------------------------------


def test_missing_edge_endpoints_detected():
    graph = make_valid_graph()
    edge = graph.edges[4]  # IMPORTS edge
    edge.source_id = "file:v1:" + "0" * 64
    edge.target_id = "file:v1:" + "1" * 64
    result = validate_graph(graph)
    assert result.valid is False
    assert "invalid_edge_source" in codes(result)
    assert "invalid_edge_target" in codes(result)


def test_cross_repository_edge_detected():
    graph = make_valid_graph()
    graph.edges[4].repository_id = "other-repo"
    result = validate_graph(graph)
    assert result.valid is False
    assert "cross_repository_reference" in codes(result)


def test_cross_repository_file_detected():
    graph = make_valid_graph()
    graph.files[0].repository_id = "other-repo"
    result = validate_graph(graph)
    assert result.valid is False
    assert "cross_repository_reference" in codes(result)


# ---------------------------------------------------------------------------
# Parent-child and structural consistency
# ---------------------------------------------------------------------------


def test_invalid_parent_child_span_detected():
    repository = make_repository()
    file = make_file(repository, "src/app.py", FILE1_HASH)
    parent = make_symbol(
        file, "Outer", "src.app.Outer", SymbolKind.CLASS, start_line=1, end_line=3
    )
    child = make_symbol(
        file, "inner", "src.app.Outer.inner", start_line=1, end_line=2
    )
    child.parent_id = parent.id
    graph = CodeGraph(
        repository=repository,
        files=[file],
        symbols=[parent, child],
        edges=[make_contains_edge(parent, child)],
    )

    # Child now outgrows the parent's span; models allow assignment mutation.
    child.end_line = 10
    result = validate_graph(graph)
    assert result.valid is False
    assert "invalid_parent_span" in codes(result)
    assert "structural_inconsistency" in codes(result)


def test_unknown_parent_reference_detected():
    graph = make_valid_graph()
    graph.symbols[0].parent_id = "symbol:v1:" + "2" * 64
    result = validate_graph(graph)
    assert result.valid is False
    assert "invalid_parent_reference" in codes(result)


def test_contains_cycle_detected():
    repository = make_repository()
    file = make_file(repository, "src/app.py", FILE1_HASH)
    first = make_symbol(file, "a", "src.app.a", start_line=1, end_line=4)
    second = make_symbol(file, "b", "src.app.a.b", start_line=2, end_line=3)
    graph = CodeGraph(
        repository=repository,
        files=[file],
        symbols=[first, second],
        edges=[
            make_contains_edge(first, second),
            make_contains_edge(second, first),
        ],
    )
    result = validate_graph(graph)
    assert result.valid is False
    assert "contains_cycle" in codes(result)


# ---------------------------------------------------------------------------
# Source spans
# ---------------------------------------------------------------------------


def test_invalid_edge_source_span_detected():
    graph = make_valid_graph()
    graph.edges[5].start_line = 0  # invalid: 1-based only
    result = validate_graph(graph)
    assert result.valid is False
    assert "invalid_source_span" in codes(result)


def test_invalid_symbol_source_span_detected():
    graph = make_valid_graph()
    graph.symbols[0].end_line = 0  # invalid: below start_line
    result = validate_graph(graph)
    assert result.valid is False
    assert "invalid_source_span" in codes(result)


# ---------------------------------------------------------------------------
# Provenance and file hashes
# ---------------------------------------------------------------------------


def test_missing_edge_provenance_data_detected():
    graph = make_valid_graph()
    graph.edges[4].source_file = None
    graph.edges[4].source_hash = None
    result = validate_graph(graph)
    assert result.valid is False
    assert "missing_provenance_data" in codes(result)


def test_edge_source_hash_mismatch_detected():
    graph = make_valid_graph()
    graph.edges[4].source_hash = sha256_hex("different bytes")
    result = validate_graph(graph)
    assert result.valid is False
    assert "edge_source_hash_mismatch" in codes(result)


def test_symbol_source_hash_mismatch_detected():
    graph = make_valid_graph()
    graph.symbols[0].source_hash = sha256_hex("different bytes")
    result = validate_graph(graph)
    assert result.valid is False
    assert "symbol_source_hash_mismatch" in codes(result)


def test_unknown_edge_source_file_detected():
    graph = make_valid_graph()
    graph.edges[4].source_file = "src/nope.py"
    result = validate_graph(graph)
    assert result.valid is False
    assert "edge_source_file_unknown" in codes(result)


def test_wrong_provenance_kind_detected():
    graph = make_valid_graph()
    graph.edges[4].provenance_kind = ProvenanceKind.DECLARATION
    result = validate_graph(graph)
    assert result.valid is False
    assert "invalid_provenance" in codes(result)


def test_self_referencing_edge_detected():
    graph = make_valid_graph()
    graph.edges[4].target_id = graph.edges[4].source_id
    result = validate_graph(graph)
    assert result.valid is False
    assert "self_referencing_edge" in codes(result)


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_deterministic_diagnostic_ordering():
    graph = make_valid_graph()
    graph.edges[4].repository_id = "other-repo"
    graph.symbols[0].source_hash = sha256_hex("different bytes")

    first = validate_graph(graph)
    second = validate_graph(graph)

    def diagnostic_tuples(result):
        return [
            (d.code, d.message, d.severity.value, d.entity_id)
            for d in result.errors + result.warnings
        ]

    assert diagnostic_tuples(first) == diagnostic_tuples(second)


# ---------------------------------------------------------------------------
# Fail-safe behaviour
# ---------------------------------------------------------------------------


def test_validate_graph_rejects_non_graph_input():
    with pytest.raises(TypeError):
        validate_graph(object())


def test_model_still_enforces_impossible_edges():
    repository = make_repository()
    first = make_file(repository, "src/app.py", FILE1_HASH)
    second = make_file(repository, "src/util.py", FILE2_HASH)
    with pytest.raises(Exception):
        GraphEdge(
            repository_id="test-repo",
            source_id=first.id,
            target_id=second.id,
            kind=EdgeKind.CALLS,
            provenance_kind=ProvenanceKind.CALL_SITE,
            source_file="src/app.py",
            start_line=1,
            end_line=1,
            start_column=1,
            end_column=5,
            source_hash=FILE1_HASH,
        )
