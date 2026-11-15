"""Phase 11.1 -- Tests for KiteHut Code Graph data models.

These tests exercise only the model contracts and deterministic identity
helpers. No discovery, extraction, traversal, serialization or database code is
involved.
"""

import json

import pytest
from pydantic import ValidationError

from app.code_graph import (
    CODE_GRAPH_SCHEMA_VERSION,
    CallSite,
    CodeGraph,
    DiagnosticSeverity,
    EdgeKind,
    EvidenceConfidence,
    FileNode,
    GraphBuildResult,
    GraphBuildStatus,
    GraphDiagnostic,
    GraphEdge,
    GraphValidationResult,
    ImportReference,
    LanguageCoverage,
    NodeKind,
    ProvenanceKind,
    RepositoryNode,
    ResolutionKind,
    SourceFile,
    SymbolDeclaration,
    SymbolKind,
    SymbolNode,
    canonical_json,
    compute_edge_id,
    compute_file_id,
    compute_repository_id,
    compute_symbol_id,
    normalize_origin,
    normalize_repository_path,
    sha256_hex,
)


FILE_HASH = sha256_hex("value = 1\n")
SOURCE_DIGEST = sha256_hex("repository snapshot")
REPO_ID = compute_repository_id(origin="https://github.com/KiteHut/KiteHut.git")


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def make_repository(
    repository_id: str = REPO_ID,
    root_path: str = "C:\\repos\\KiteHut",
) -> RepositoryNode:
    return RepositoryNode(
        repository_id=repository_id,
        name="KiteHut",
        root_path=root_path,
        source_digest=SOURCE_DIGEST,
    )


def make_file(
    repository: RepositoryNode,
    relative_path: str = "src/app.py",
    content_hash: str = FILE_HASH,
) -> FileNode:
    return FileNode(
        repository_id=repository.repository_id,
        relative_path=relative_path,
        language="python",
        content_hash=content_hash,
        line_count=2,
        byte_size=11,
    )


def make_symbol(
    file: FileNode,
    name: str = "run",
    qualified_name: str = "src.app.run",
    kind: SymbolKind = SymbolKind.FUNCTION,
    occurrence_ordinal: int = 0,
    start_line: int = 1,
    end_line: int = 2,
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
        end_column=10,
        source_hash=file.content_hash,
        occurrence_ordinal=occurrence_ordinal,
    )


def make_containment_edge(
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


def make_contains_edge(source: SymbolNode, target: SymbolNode) -> GraphEdge:
    return GraphEdge(
        repository_id=source.repository_id,
        source_id=source.id,
        target_id=target.id,
        kind=EdgeKind.CONTAINS,
        provenance_kind=ProvenanceKind.DECLARATION,
        source_file=target.relative_path,
        start_line=target.start_line,
        end_line=target.end_line,
        source_hash=target.source_hash,
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
        start_line=3,
        end_line=3,
        start_column=4,
        end_column=10,
        source_hash=caller.source_hash,
    )


def make_graph_with_edges() -> CodeGraph:
    repository = make_repository()
    first = make_file(repository)
    second = make_file(repository, relative_path="src/util.py", content_hash=sha256_hex("x"))
    first_symbol = make_symbol(first)
    second_symbol = make_symbol(
        second,
        name="helper",
        qualified_name="src.util.helper",
        start_line=1,
        end_line=1,
    )
    edges = [
        make_containment_edge(repository, first),
        make_containment_edge(repository, second),
        make_defines_edge(first, first_symbol),
        make_defines_edge(second, second_symbol),
        make_imports_edge(first, second),
        make_calls_edge(first_symbol, second_symbol),
    ]
    return CodeGraph(
        repository=repository,
        files=[first, second],
        symbols=[first_symbol, second_symbol],
        edges=edges,
    )


def error_diagnostic(code: str = "syntax_error") -> GraphDiagnostic:
    return GraphDiagnostic(
        code=code,
        message="Could not parse file.",
        severity=DiagnosticSeverity.ERROR,
        relative_path="src/app.py",
        line=3,
    )


def fatal_diagnostic(code: str = "invalid_root") -> GraphDiagnostic:
    return GraphDiagnostic(
        code=code,
        message="Repository root does not exist.",
        severity=DiagnosticSeverity.FATAL,
    )


# ---------------------------------------------------------------------------
# Enum serialization
# ---------------------------------------------------------------------------


def test_enum_values_and_json_serialization():
    assert NodeKind.REPOSITORY.value == "repository"
    assert NodeKind.FILE.value == "file"
    assert NodeKind.SYMBOL.value == "symbol"
    assert SymbolKind.ASYNC_FUNCTION.value == "async_function"
    assert EdgeKind.CONTAINS.value == "contains"
    assert EdgeKind.CALLS.value == "calls"
    assert ResolutionKind.UNRESOLVED.value == "unresolved"
    assert EvidenceConfidence.EXACT.value == "exact"
    assert ProvenanceKind.IMPORT_STATEMENT.value == "import_statement"
    assert GraphBuildStatus.PARTIAL.value == "partial"

    repository = make_repository()
    file = make_file(repository)
    edge = make_containment_edge(repository, file)
    payload = edge.model_dump(mode="json")

    assert payload["kind"] == "contains"
    assert payload["provenance_kind"] == "discovered_path"
    assert payload["confidence"] == "high"
    assert payload["resolution"] == "resolved"
    assert json.loads(edge.model_dump_json())["kind"] == "contains"

    symbol = make_symbol(file)
    assert symbol.model_dump(mode="json")["kind"] == "function"
    assert repository.node_kind == NodeKind.REPOSITORY
    assert file.node_kind == NodeKind.FILE
    assert symbol.node_kind == NodeKind.SYMBOL


def test_canonical_json_sorts_compacts_and_normalizes_unicode():
    payload = canonical_json({"b": 1, "a": "cafe\u0301"})
    assert payload == '{"a":"café","b":1}'
    assert "\\u" not in payload
    assert sha256_hex("abc") == (
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    )


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------


def test_paths_are_normalized_to_posix_nfc_and_preserve_case():
    assert normalize_repository_path("src\\pkg\\.\\Module.py") == "src/pkg/Module.py"
    assert normalize_repository_path("cafe\u0301.py") == "café.py"
    assert normalize_repository_path("SRC/App.py") == "SRC/App.py"

    repository = make_repository()
    file = FileNode(
        repository_id=repository.repository_id,
        relative_path="src\\Pkg\\Util.py",
        language="python",
        content_hash=FILE_HASH,
        line_count=1,
        byte_size=10,
    )
    assert file.relative_path == "src/Pkg/Util.py"


@pytest.mark.parametrize(
    "path",
    [
        "/etc/passwd",
        "C:\\Windows\\system.ini",
        "C:/Windows/system.ini",
        "//server/share/file.py",
        "../outside.py",
        "src/../../outside.py",
        "src/\x00bad.py",
        "",
        "   ",
    ],
)
def test_absolute_escaping_and_empty_paths_are_rejected(path):
    with pytest.raises((ValidationError, ValueError)):
        normalize_repository_path(path)

    with pytest.raises(ValidationError):
        FileNode(
            repository_id=REPO_ID,
            relative_path=path,
            language="python",
            content_hash=FILE_HASH,
            line_count=1,
            byte_size=1,
        )


# ---------------------------------------------------------------------------
# Hashes and identifiers
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad_hash",
    [
        "",
        "a" * 63,
        "a" * 65,
        "A" * 64,
        "g" * 64,
        "sha256:" + "a" * 64,
    ],
)
def test_invalid_hashes_are_rejected(bad_hash):
    with pytest.raises(ValidationError):
        FileNode(
            repository_id=REPO_ID,
            relative_path="src/app.py",
            language="python",
            content_hash=bad_hash,
            line_count=1,
            byte_size=1,
        )

    with pytest.raises(ValidationError):
        RepositoryNode(
            repository_id=REPO_ID,
            name="KiteHut",
            source_digest=bad_hash,
        )


def test_deterministic_ids_are_versioned_and_sha256_shaped():
    repository = make_repository()
    file = make_file(repository)
    symbol = make_symbol(file)
    edge = make_containment_edge(repository, file)

    assert file.id.startswith("file:v1:")
    assert symbol.id.startswith("symbol:v1:")
    assert edge.id.startswith("edge:v1:")
    assert file.id == compute_file_id(repository.repository_id, file.relative_path)
    assert symbol.id == compute_symbol_id(
        repository.repository_id,
        symbol.relative_path,
        symbol.qualified_name,
        symbol.kind,
        symbol.occurrence_ordinal,
    )
    assert len(file.id.split(":")[-1]) == 64


def test_mismatched_deterministic_ids_are_rejected():
    repository = make_repository()
    file = make_file(repository)
    symbol = make_symbol(file)

    with pytest.raises(ValidationError):
        FileNode(
            id="file:v1:" + "b" * 64,
            repository_id=repository.repository_id,
            relative_path=file.relative_path,
            language="python",
            content_hash=FILE_HASH,
            line_count=1,
            byte_size=1,
        )

    with pytest.raises(ValidationError):
        SymbolNode(
            id="symbol:v1:" + "b" * 64,
            repository_id=symbol.repository_id,
            file_id=symbol.file_id,
            relative_path=symbol.relative_path,
            name=symbol.name,
            qualified_name=symbol.qualified_name,
            kind=symbol.kind,
            start_line=1,
            end_line=1,
            source_hash=symbol.source_hash,
        )

    with pytest.raises(ValidationError):
        GraphEdge(
            id="edge:v1:" + "b" * 64,
            repository_id=repository.repository_id,
            source_id=repository.repository_id,
            target_id=file.id,
            kind=EdgeKind.CONTAINS,
            provenance_kind=ProvenanceKind.DISCOVERED_PATH,
            source_file=file.relative_path,
            source_hash=file.content_hash,
        )

    with pytest.raises(ValidationError):
        RepositoryNode(
            id="repo:v1:" + "b" * 64,
            repository_id=repository.repository_id,
            name="KiteHut",
            source_digest=SOURCE_DIGEST,
        )


def test_duplicate_symbol_names_receive_distinct_deterministic_ids():
    repository = make_repository()
    file = make_file(repository)

    first = make_symbol(file, occurrence_ordinal=0)
    second = make_symbol(file, occurrence_ordinal=1)
    first_again = make_symbol(file, occurrence_ordinal=0)

    assert first.id != second.id
    assert first.id == first_again.id

    different_scope = make_symbol(
        file,
        qualified_name="src.app.Inner.run",
        occurrence_ordinal=0,
    )
    different_kind = make_symbol(
        file,
        kind=SymbolKind.ASYNC_FUNCTION,
        occurrence_ordinal=0,
    )
    assert len({first.id, second.id, different_scope.id, different_kind.id}) == 4


def test_ids_are_stable_across_absolute_roots():
    repository_a = make_repository(root_path="C:\\repos\\clone-a")
    repository_b = make_repository(root_path="/home/other/clone-b")
    file_a = make_file(repository_a)
    file_b = make_file(repository_b)
    symbol_a = make_symbol(file_a)
    symbol_b = make_symbol(file_b)
    edge_a = make_containment_edge(repository_a, file_a)
    edge_b = make_containment_edge(repository_b, file_b)

    assert repository_a.repository_id == repository_b.repository_id
    assert file_a.id == file_b.id
    assert symbol_a.id == symbol_b.id
    assert edge_a.id == edge_b.id
    for identifier in (file_a.id, symbol_a.id, edge_a.id):
        assert "C:" not in identifier
        assert "/home" not in identifier
        assert "clone" not in identifier


# ---------------------------------------------------------------------------
# Repository identity and origin normalization
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("origin", "expected"),
    [
        (
            "https://user:pass@GitHub.com:443/Owner/Repo.git?ref=main#readme",
            "https://github.com/Owner/Repo",
        ),
        ("http://github.com/Owner/Repo.git", "https://github.com/Owner/Repo"),
        ("git@github.com:Owner/Repo.git", "https://github.com/Owner/Repo"),
        (
            "ssh://git@github.com:22/Owner/Repo.git",
            "https://github.com/Owner/Repo",
        ),
        ("git://github.com/Owner/Repo", "https://github.com/Owner/Repo"),
        ("https://github.com:8443/Owner/Repo", "https://github.com:8443/Owner/Repo"),
    ],
)
def test_repository_origin_normalization(origin, expected):
    assert normalize_origin(origin) == expected


def test_equivalent_origins_produce_the_same_repository_id():
    https_id = compute_repository_id(origin="https://github.com/Owner/Repo.git")
    scp_id = compute_repository_id(origin="git@github.com:Owner/Repo.git")

    assert https_id == scp_id
    assert https_id.startswith("repo:v1:")
    assert normalize_origin("https://github.com/Owner/Repo.git") == (
        "https://github.com/Owner/Repo"
    )


def test_repository_identity_precedence():
    explicit = "repo:v1:" + "c" * 64
    file_hash = sha256_hex("file")

    assert (
        compute_repository_id(
            explicit,
            origin="https://github.com/Owner/Repo",
            repository_key="kitehut",
            files=[("a.py", file_hash)],
        )
        == explicit
    )

    origin_id = compute_repository_id(origin="https://github.com/Owner/Repo")
    key_id = compute_repository_id(repository_key="Owner/Repo")
    assert origin_id.startswith("repo:v1:")
    assert key_id.startswith("repo:v1:")
    assert origin_id != key_id

    snapshot_first = compute_repository_id(
        files=[("b.py", sha256_hex("b")), ("a.py", file_hash)]
    )
    snapshot_second = compute_repository_id(
        files=[("a.py", file_hash), ("b.py", sha256_hex("b"))]
    )
    assert snapshot_first == snapshot_second
    assert snapshot_first.startswith("snapshot:v1:")
    assert snapshot_first != compute_repository_id(
        files=[("a.py", sha256_hex("changed"))]
    )


@pytest.mark.parametrize(
    "origin",
    [
        "C:\\repos\\KiteHut",
        "/home/user/repos/KiteHut",
        "not-a-url",
        "ftp://github.com/Owner/Repo",
        "https:///Owner/Repo",
        "https://github.com/Owner/../Repo",
    ],
)
def test_invalid_repository_origins_are_rejected(origin):
    with pytest.raises(ValueError):
        normalize_origin(origin)


def test_repository_identity_is_required():
    with pytest.raises(ValueError):
        compute_repository_id()

    with pytest.raises(ValidationError):
        RepositoryNode(repository_id="", name="KiteHut", source_digest=SOURCE_DIGEST)

    with pytest.raises(ValidationError):
        RepositoryNode(
            repository_id="C:\\repos\\KiteHut",
            name="KiteHut",
            source_digest=SOURCE_DIGEST,
        )


# ---------------------------------------------------------------------------
# Source spans
# ---------------------------------------------------------------------------


def test_symbol_and_source_record_spans_are_one_based_inclusive():
    declaration = SymbolDeclaration(
        relative_path="src/app.py",
        name="run",
        qualified_name="src.app.run",
        kind=SymbolKind.FUNCTION,
        start_line=1,
        end_line=3,
        start_column=1,
        end_column=8,
        occurrence_ordinal=0,
    )
    assert declaration.end_line == 3

    with pytest.raises(ValidationError):
        SymbolDeclaration(
            relative_path="src/app.py",
            name="run",
            qualified_name="src.app.run",
            kind=SymbolKind.FUNCTION,
            start_line=0,
            end_line=3,
        )

    with pytest.raises(ValidationError):
        SymbolDeclaration(
            relative_path="src/app.py",
            name="run",
            qualified_name="src.app.run",
            kind=SymbolKind.FUNCTION,
            start_line=5,
            end_line=3,
        )

    with pytest.raises(ValidationError):
        SymbolDeclaration(
            relative_path="src/app.py",
            name="run",
            qualified_name="src.app.run",
            kind=SymbolKind.FUNCTION,
            start_line=2,
            end_line=2,
            start_column=8,
            end_column=2,
        )

    with pytest.raises(ValidationError):
        SymbolDeclaration(
            relative_path="src/app.py",
            name="run",
            qualified_name="src.app.run",
            kind=SymbolKind.FUNCTION,
            start_line=2,
            end_line=2,
            start_column=1,
        )


def test_import_and_call_sites_require_exact_spans():
    """Import and call sites require exact spans."""
    reference = ImportReference(
        relative_path="src/app.py",
        module="os",
        start_line=1,
        end_line=1,
        start_column=1,
        end_column=10,
        source_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    )
    assert reference.module == "os"
    assert reference.imported_names == []

    call = CallSite(
        relative_path="src/app.py",
        callee_name="run",
        start_line=2,
        end_line=2,
        start_column=5,
        end_column=9,
        source_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    )
    assert call.callee_name == "run"

    with pytest.raises(ValidationError):
        ImportReference(
            relative_path="../outside.py",
            module="os",
            start_line=1,
            end_line=1,
            start_column=1,
            end_column=10,
            source_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        )

    with pytest.raises(ValidationError):
        ImportReference(
            relative_path="src/app.py",
            module="os",
            start_line=1,
            end_line=1,
            start_column=1,
            end_column=10,
            source_hash="not-a-hash",
        )

    with pytest.raises(ValidationError):
        CallSite(
            relative_path="src/app.py",
            callee_name="run",
            start_line=1,
            end_line=1,
            start_column=0,
            end_column=4,
            source_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        )


# ---------------------------------------------------------------------------
# Construction, round trips and defaults
# ---------------------------------------------------------------------------


def test_graph_construction_and_round_trip():
    graph = make_graph_with_edges()
    assert graph.schema_version == CODE_GRAPH_SCHEMA_VERSION
    assert graph.source_digest == SOURCE_DIGEST
    assert len(graph.files) == 2
    assert len(graph.symbols) == 2
    assert len(graph.edges) == 6

    restored = CodeGraph.model_validate_json(graph.model_dump_json())
    assert restored == graph
    assert restored.edges[0].provenance_kind == ProvenanceKind.DISCOVERED_PATH
    assert restored.symbols[0].kind == SymbolKind.FUNCTION


def test_individual_models_round_trip():
    repository = make_repository()
    file = make_file(repository)
    symbol = make_symbol(file)

    assert FileNode.model_validate_json(file.model_dump_json()) == file
    assert SymbolNode.model_validate_json(symbol.model_dump_json()) == symbol
    assert RepositoryNode.model_validate_json(
        repository.model_dump_json()
    ) == repository


def test_default_collections_are_independent():
    graph_one = CodeGraph(repository=make_repository())
    graph_two = CodeGraph(repository=make_repository(root_path="D:\\other"))

    graph_one.files.append(make_file(graph_one.repository))
    assert graph_two.files == []
    assert graph_one.files is not graph_two.files
    assert graph_one.symbols is not graph_two.symbols
    assert graph_one.edges is not graph_two.edges

    first_import = ImportReference(
        relative_path="src/app.py",
        module="os",
        start_line=1,
        end_line=1,
        start_column=1,
        end_column=10,
        source_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    )
    second_import = ImportReference(
        relative_path="src/app.py",
        module="sys",
        start_line=1,
        end_line=1,
        start_column=1,
        end_column=10,
        source_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    )
    first_import.imported_names.append("path")
    assert second_import.imported_names == []

    result_one = GraphBuildResult(
        status=GraphBuildStatus.FAILED, errors=[fatal_diagnostic()]
    )
    result_two = GraphBuildResult(
        status=GraphBuildStatus.FAILED, errors=[fatal_diagnostic("other")]
    )
    assert result_one.warnings is not result_two.warnings
    assert result_one.unresolved_imports is not result_two.unresolved_imports
    assert result_one.unresolved_calls is not result_two.unresolved_calls


@pytest.mark.parametrize("schema_version", [0, -1])
def test_invalid_schema_versions_are_rejected(schema_version):
    with pytest.raises(ValidationError):
        CodeGraph(
            schema_version=schema_version,
            repository=make_repository(),
        )


def test_graph_rejects_cross_repository_entities_and_duplicate_ids():
    repository = make_repository()
    other_repository = make_repository(
        repository_id=compute_repository_id(origin="https://github.com/Other/Repo"),
        root_path="D:\\other",
    )
    foreign_file = make_file(other_repository)

    with pytest.raises(ValidationError):
        CodeGraph(repository=repository, files=[foreign_file])

    same_file = make_file(repository)
    with pytest.raises(ValidationError):
        CodeGraph(repository=repository, files=[same_file, same_file])


def test_graph_source_digest_must_match_repository():
    repository = make_repository()

    with pytest.raises(ValidationError):
        CodeGraph(repository=repository, source_digest=sha256_hex("different"))

    graph = CodeGraph(repository=repository)
    assert graph.source_digest == repository.source_digest


# ---------------------------------------------------------------------------
# Edge provenance rules
# ---------------------------------------------------------------------------


def test_repository_containment_does_not_require_a_statement_span():
    repository = make_repository()
    file = make_file(repository)

    edge = make_containment_edge(repository, file)

    assert edge.start_line is None
    assert edge.end_line is None
    assert edge.provenance_kind == ProvenanceKind.DISCOVERED_PATH
    assert edge.source_file == "src/app.py"
    assert edge.source_hash == file.content_hash


def test_repository_containment_rejects_wrong_provenance_or_missing_hash():
    repository = make_repository()
    file = make_file(repository)

    with pytest.raises(ValidationError):
        GraphEdge(
            repository_id=repository.repository_id,
            source_id=repository.repository_id,
            target_id=file.id,
            kind=EdgeKind.CONTAINS,
            provenance_kind=ProvenanceKind.DECLARATION,
            source_file=file.relative_path,
            source_hash=file.content_hash,
        )

    with pytest.raises(ValidationError):
        GraphEdge(
            repository_id=repository.repository_id,
            source_id=repository.repository_id,
            target_id=file.id,
            kind=EdgeKind.CONTAINS,
            provenance_kind=ProvenanceKind.DISCOVERED_PATH,
            source_file=file.relative_path,
        )

    symbol = make_symbol(file)
    with pytest.raises(ValidationError):
        GraphEdge(
            repository_id=repository.repository_id,
            source_id=repository.repository_id,
            target_id=symbol.id,
            kind=EdgeKind.CONTAINS,
            provenance_kind=ProvenanceKind.DISCOVERED_PATH,
            source_file=file.relative_path,
            source_hash=file.content_hash,
        )


def test_lexical_containment_requires_child_declaration_provenance():
    repository = make_repository()
    file = make_file(repository)
    parent = make_symbol(file, name="Outer", qualified_name="src.app.Outer", kind=SymbolKind.CLASS)
    child = make_symbol(
        file,
        name="inner",
        qualified_name="src.app.Outer.inner",
        start_line=2,
        end_line=2,
    )

    edge = make_contains_edge(parent, child)
    assert edge.provenance_kind == ProvenanceKind.DECLARATION
    assert (edge.start_line, edge.end_line) == (2, 2)

    with pytest.raises(ValidationError):
        GraphEdge(
            repository_id=repository.repository_id,
            source_id=parent.id,
            target_id=child.id,
            kind=EdgeKind.CONTAINS,
            provenance_kind=ProvenanceKind.DECLARATION,
            source_file=child.relative_path,
            source_hash=child.source_hash,
        )


def test_defines_requires_declaration_span_and_hash():
    repository = make_repository()
    file = make_file(repository)
    symbol = make_symbol(file)

    edge = make_defines_edge(file, symbol)
    assert edge.provenance_kind == ProvenanceKind.DECLARATION

    with pytest.raises(ValidationError):
        GraphEdge(
            repository_id=repository.repository_id,
            source_id=file.id,
            target_id=symbol.id,
            kind=EdgeKind.DEFINES,
            provenance_kind=ProvenanceKind.DECLARATION,
            source_file=file.relative_path,
            source_hash=file.content_hash,
        )

    with pytest.raises(ValidationError):
        GraphEdge(
            repository_id=repository.repository_id,
            source_id=file.id,
            target_id=symbol.id,
            kind=EdgeKind.DEFINES,
            provenance_kind=ProvenanceKind.DISCOVERED_PATH,
            source_file=file.relative_path,
            start_line=1,
            end_line=1,
            source_hash=file.content_hash,
        )


def test_import_and_call_edges_require_exact_statement_spans():
    repository = make_repository()
    source_file = make_file(repository)
    target_file = make_file(
        repository, relative_path="src/util.py", content_hash=sha256_hex("util")
    )
    caller = make_symbol(source_file)
    callee = make_symbol(
        target_file, name="helper", qualified_name="src.util.helper"
    )

    imports_edge = make_imports_edge(source_file, target_file)
    calls_edge = make_calls_edge(caller, callee)

    assert imports_edge.provenance_kind == ProvenanceKind.IMPORT_STATEMENT
    assert (imports_edge.start_line, imports_edge.start_column) == (1, 1)
    assert calls_edge.provenance_kind == ProvenanceKind.CALL_SITE
    assert (calls_edge.start_line, calls_edge.start_column) == (3, 4)

    for edge_kwargs in (
        dict(
            source_id=source_file.id,
            target_id=target_file.id,
            kind=EdgeKind.IMPORTS,
            provenance_kind=ProvenanceKind.IMPORT_STATEMENT,
            source_file=source_file.relative_path,
            source_hash=source_file.content_hash,
        ),
        dict(
            source_id=caller.id,
            target_id=callee.id,
            kind=EdgeKind.CALLS,
            provenance_kind=ProvenanceKind.CALL_SITE,
            source_file=caller.relative_path,
            source_hash=caller.source_hash,
        ),
    ):
        with pytest.raises(ValidationError):
            GraphEdge(repository_id=repository.repository_id, **edge_kwargs)

    with pytest.raises(ValidationError):
        GraphEdge(
            repository_id=repository.repository_id,
            source_id=source_file.id,
            target_id=target_file.id,
            kind=EdgeKind.IMPORTS,
            provenance_kind=ProvenanceKind.IMPORT_STATEMENT,
            source_file=source_file.relative_path,
            start_line=1,
            end_line=1,
            start_column=1,
            end_column=12,
            source_hash=source_file.content_hash,
            id="edge:v1:" + "d" * 64,
        )


def test_edge_endpoint_kinds_are_enforced():
    repository = make_repository()
    file = make_file(repository)
    symbol = make_symbol(file)

    with pytest.raises(ValidationError):
        GraphEdge(
            repository_id=repository.repository_id,
            source_id=file.id,
            target_id=symbol.id,
            kind=EdgeKind.CALLS,
            provenance_kind=ProvenanceKind.CALL_SITE,
            source_file=file.relative_path,
            start_line=1,
            end_line=1,
            start_column=1,
            end_column=5,
            source_hash=file.content_hash,
        )


# ---------------------------------------------------------------------------
# Build status invariants
# ---------------------------------------------------------------------------


def complete_coverage(**overrides) -> LanguageCoverage:
    values = dict(
        language="python",
        supported=True,
        discovered_files=1,
        analyzed_files=1,
        skipped_files=0,
    )
    values.update(overrides)
    return LanguageCoverage(**values)


def test_complete_build_requires_graph_and_full_coverage():
    graph = make_graph_with_edges()
    result = GraphBuildResult(
        status=GraphBuildStatus.COMPLETE,
        graph=graph,
        coverage=[complete_coverage(discovered_files=2, analyzed_files=2)],
        file_count=2,
        symbol_count=2,
        edge_count=6,
    )
    assert result.status == GraphBuildStatus.COMPLETE

    with pytest.raises(ValidationError):
        GraphBuildResult(status=GraphBuildStatus.COMPLETE, coverage=[complete_coverage()])

    with pytest.raises(ValidationError):
        GraphBuildResult(
            status=GraphBuildStatus.COMPLETE,
            graph=graph,
            file_count=2,
            symbol_count=2,
            edge_count=6,
        )

    with pytest.raises(ValidationError):
        GraphBuildResult(
            status=GraphBuildStatus.COMPLETE,
            graph=graph,
            coverage=[complete_coverage()],
            file_count=2,
            symbol_count=2,
            edge_count=6,
            truncated=True,
        )

    with pytest.raises(ValidationError):
        GraphBuildResult(
            status=GraphBuildStatus.COMPLETE,
            graph=graph,
            coverage=[complete_coverage()],
            file_count=2,
            symbol_count=2,
            edge_count=6,
            errors=[error_diagnostic()],
        )

    with pytest.raises(ValidationError):
        GraphBuildResult(
            status=GraphBuildStatus.COMPLETE,
            graph=graph,
            coverage=[complete_coverage(discovered_files=2, analyzed_files=1)],
            file_count=2,
            symbol_count=2,
            edge_count=6,
        )


def test_complete_build_ignores_unsupported_language_coverage():
    graph = make_graph_with_edges()
    result = GraphBuildResult(
        status=GraphBuildStatus.COMPLETE,
        graph=graph,
        coverage=[
            complete_coverage(discovered_files=2, analyzed_files=2),
            LanguageCoverage(
                language="javascript",
                supported=False,
                discovered_files=3,
                analyzed_files=0,
                skipped_files=3,
            ),
        ],
        file_count=2,
        symbol_count=2,
        edge_count=6,
    )
    assert result.status == GraphBuildStatus.COMPLETE


def test_partial_build_requires_graph_and_a_real_issue():
    graph = make_graph_with_edges()

    with_error = GraphBuildResult(
        status=GraphBuildStatus.PARTIAL,
        graph=graph,
        coverage=[complete_coverage(discovered_files=2, analyzed_files=1)],
        file_count=2,
        symbol_count=2,
        edge_count=6,
        errors=[error_diagnostic()],
    )
    assert with_error.status == GraphBuildStatus.PARTIAL

    truncated = GraphBuildResult(
        status=GraphBuildStatus.PARTIAL,
        graph=graph,
        truncated=True,
        file_count=2,
        symbol_count=2,
        edge_count=6,
    )
    assert truncated.truncated is True

    gap_only = GraphBuildResult(
        status=GraphBuildStatus.PARTIAL,
        graph=graph,
        coverage=[complete_coverage(discovered_files=2, analyzed_files=1)],
        file_count=2,
        symbol_count=2,
        edge_count=6,
    )
    assert gap_only.status == GraphBuildStatus.PARTIAL

    with pytest.raises(ValidationError):
        GraphBuildResult(
            status=GraphBuildStatus.PARTIAL,
            graph=graph,
            file_count=2,
            symbol_count=2,
            edge_count=6,
        )

    with pytest.raises(ValidationError):
        GraphBuildResult(
            status=GraphBuildStatus.PARTIAL,
            file_count=2,
            symbol_count=2,
            edge_count=6,
            errors=[error_diagnostic()],
        )


def test_unresolved_relationships_do_not_make_a_build_partial():
    graph = make_graph_with_edges()
    unresolved_warning = GraphDiagnostic(
        code="unresolved_import",
        message="External import was not resolved.",
        severity=DiagnosticSeverity.INFO,
        relative_path="src/app.py",
        line=1,
    )

    with pytest.raises(ValidationError):
        GraphBuildResult(
            status=GraphBuildStatus.PARTIAL,
            graph=graph,
            file_count=2,
            symbol_count=2,
            edge_count=6,
            unresolved_imports=[unresolved_warning],
            unresolved_calls=[unresolved_warning],
        )

    complete = GraphBuildResult(
        status=GraphBuildStatus.COMPLETE,
        graph=graph,
        coverage=[complete_coverage(discovered_files=2, analyzed_files=2)],
        file_count=2,
        symbol_count=2,
        edge_count=6,
        unresolved_imports=[unresolved_warning],
        unresolved_calls=[unresolved_warning],
    )
    assert complete.status == GraphBuildStatus.COMPLETE


def test_failed_build_requires_no_graph_and_a_fatal_diagnostic():
    result = GraphBuildResult(
        status=GraphBuildStatus.FAILED,
        errors=[fatal_diagnostic()],
    )
    assert result.graph is None

    with pytest.raises(ValidationError):
        GraphBuildResult(status=GraphBuildStatus.FAILED)

    with pytest.raises(ValidationError):
        GraphBuildResult(
            status=GraphBuildStatus.FAILED,
            errors=[error_diagnostic()],
        )

    with pytest.raises(ValidationError):
        GraphBuildResult(
            status=GraphBuildStatus.FAILED,
            graph=make_graph_with_edges(),
            file_count=2,
            symbol_count=2,
            edge_count=6,
            errors=[fatal_diagnostic()],
        )


def test_build_counts_must_match_the_graph():
    graph = make_graph_with_edges()

    with pytest.raises(ValidationError):
        GraphBuildResult(
            status=GraphBuildStatus.COMPLETE,
            graph=graph,
            coverage=[complete_coverage(discovered_files=2, analyzed_files=2)],
            file_count=1,
            symbol_count=2,
            edge_count=6,
        )


def test_build_errors_must_use_error_or_fatal_severity():
    with pytest.raises(ValidationError):
        GraphBuildResult(
            status=GraphBuildStatus.FAILED,
            errors=[
                GraphDiagnostic(
                    code="warning_as_error",
                    message="Wrong severity.",
                    severity=DiagnosticSeverity.WARNING,
                )
            ],
        )


# ---------------------------------------------------------------------------
# Validation result invariants
# ---------------------------------------------------------------------------


def test_validation_result_consistency():
    valid = GraphValidationResult(valid=True, checked_nodes=2, checked_edges=1)
    assert valid.errors == []

    invalid = GraphValidationResult(
        valid=False,
        errors=[error_diagnostic("dangling_endpoint")],
        checked_nodes=2,
        checked_edges=1,
    )
    assert invalid.valid is False

    with pytest.raises(ValidationError):
        GraphValidationResult(valid=True, errors=[error_diagnostic()])

    with pytest.raises(ValidationError):
        GraphValidationResult(valid=False)

    with pytest.raises(ValidationError):
        GraphValidationResult(
            valid=False,
            warnings=[error_diagnostic()],
            errors=[error_diagnostic()],
        )


# ---------------------------------------------------------------------------
# Internal source records
# ---------------------------------------------------------------------------


def test_source_file_record_normalizes_path_and_requires_valid_hash():
    source = SourceFile(
        relative_path="src\\pkg\\mod.py",
        language="python",
        content="value = 1\n",
        content_hash=FILE_HASH,
        byte_size=10,
        line_count=1,
    )
    assert source.relative_path == "src/pkg/mod.py"

    with pytest.raises(ValidationError):
        SourceFile(
            relative_path="../escape.py",
            language="python",
            content="",
            content_hash=FILE_HASH,
            byte_size=0,
            line_count=0,
        )

    with pytest.raises(ValidationError):
        SourceFile(
            relative_path="src/pkg/mod.py",
            language="python",
            content="",
            content_hash="not-a-hash",
            byte_size=0,
            line_count=0,
        )


def test_import_reference_requires_source_hash():
    """ImportReference must have a valid source_hash."""
    with pytest.raises(ValidationError):
        ImportReference(
            relative_path="src/app.py",
            module="os",
            start_line=1,
            end_line=1,
            start_column=1,
            end_column=10,
        )

    valid_ref = ImportReference(
        relative_path="src/app.py",
        module="os",
        start_line=1,
        end_line=1,
        start_column=1,
        end_column=10,
        source_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    )
    assert valid_ref.source_hash == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


def test_call_site_requires_source_hash():
    """CallSite must have a valid source_hash."""
    with pytest.raises(ValidationError):
        CallSite(
            relative_path="src/app.py",
            callee_name="run",
            start_line=1,
            end_line=1,
            start_column=1,
            end_column=5,
        )

    valid_call = CallSite(
        relative_path="src/app.py",
        callee_name="run",
        start_line=1,
        end_line=1,
        start_column=1,
        end_column=5,
        source_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    )
    assert valid_call.source_hash == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"