"""Phase 11.4 -- Relationship extraction tests for KiteHut Code Graph"""

import pytest

from app.code_graph.models import (
    GraphEdge,
    GraphDiagnostic,
    GraphBuildResult,
    GraphBuildStatus,
    LanguageCoverage,
    ProvenanceKind,
    ResolutionKind,
    SymbolDeclaration,
    SymbolKind,
    compute_edge_id,
    compute_file_id,
    compute_symbol_id,
    normalize_repository_path,
    SourceFile,
    EdgeKind,
)
from app.code_graph.relationships import (
    RelationshipExtractor,
    RelationshipExtractionResult,
    _extract_imports_from_source,
    _resolve_imports_to_edges,
    _extract_calls_from_source,
    _resolve_calls_to_edges,
    _symbol_id,
)
from app.code_graph.discovery import RepositoryScanner, DEFAULT_MAX_FILES
import hashlib

# Hard-coded content hashes computed from actual source content
_INIT_HASH = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
_CALCULATOR_HASH = "f9a4367cbdbfb0d31df8a33c3844b5252f0784cd854c120c06d254300ee889ae"
_EXTERNAL_IMPORT_HASH = "06185522e4085460db5f973d6987f2c5f42519fccd56836e5e5ed9842962de8d"

# Hash for helpers.py content: "def helper_func():\n    return \"helper\""
_HELPERS_HASH = "653fd34a4706cb7a4d044adb574ea1f230ee0dd56c11aceaf2e894f6db8daf91"


def test_extractor_creates_imports_edges():
    """Test that internal package-relative imports produce valid IMPORTS edges."""
    from app.code_graph.models import SourceFile, SymbolDeclaration, SymbolKind, EdgeKind
    from app.code_graph.relationships import RelationshipExtractor

    # Source files for the mypackage package with actual content
    helper_c = "def helper_func():\n    return \"helper\""
    calc_c = "from .helpers import helper_func"

    source_files = [
        SourceFile(
            relative_path="mypackage/__init__.py",
            language="python",
            content="",
            content_hash=_INIT_HASH,
            byte_size=0,
            line_count=0,
        ),
        SourceFile(
            relative_path="mypackage/helpers.py",
            language="python",
            content=helper_c,
            content_hash=_HELPERS_HASH,
            byte_size=len(helper_c.encode("utf-8")),
            line_count=helper_c.count(chr(10)) + 1 if helper_c else 0,
        ),
        SourceFile(
            relative_path="mypackage/calculator.py",
            language="python",
            content=calc_c,
            content_hash=_CALCULATOR_HASH,
            byte_size=len(calc_c.encode("utf-8")),
            line_count=1,
        ),
    ]

    # Symbol declarations
    declarations = [
        SymbolDeclaration(
            relative_path="mypackage/helpers.py",
            name="helper_func",
            qualified_name="helper_func",
            kind=SymbolKind.FUNCTION,
            start_line=1,
            end_line=3,
            start_column=4,
            end_column=12,
            occurrence_ordinal=0,
        ),
        SymbolDeclaration(
            relative_path="mypackage/calculator.py",
            name="Calculator",
            qualified_name="Calculator",
            kind=SymbolKind.CLASS,
            start_line=2,
            end_line=6,
            start_column=4,
            end_column=12,
            occurrence_ordinal=0,
        ),
        SymbolDeclaration(
            relative_path="mypackage/calculator.py",
            name="add",
            qualified_name="Calculator.add",
            kind=SymbolKind.FUNCTION,
            start_line=4,
            end_line=4,
            start_column=8,
            end_column=16,
            occurrence_ordinal=0,
        ),
        SymbolDeclaration(
            relative_path="mypackage/calculator.py",
            name="subtract",
            qualified_name="Calculator.subtract",
            kind=SymbolKind.FUNCTION,
            start_line=5,
            end_line=5,
            start_column=8,
            end_column=20,
            occurrence_ordinal=0,
        ),
    ]

    # Extract relationships using an instantiated extractor
    extractor = RelationshipExtractor()
    result = extractor.extract(
        source_files=source_files,
        declarations=declarations,
        repository_id="test-repo",
    )

    # Should produce IMPORTS edge from calculator.py to helpers.py
    import_edges = [e for e in result.edges if e.kind == EdgeKind.IMPORTS]
    assert len(import_edges) >= 1, "Expected at least 1 IMPORTS edge"

    # Find the edge from calculator.py to helpers.py
    calc_helper_edge = None
    for edge in import_edges:
        if edge.source_id.startswith("file:v1:") and edge.target_id.startswith("file:v1:"):
            calc_helper_edge = edge
            break

    assert calc_helper_edge is not None, "Expected IMPORTS edge from calculator.py to helpers.py"

    # Verify the edge has proper provenance
    assert calc_helper_edge.provenance_kind == "import_statement"
    assert calc_helper_edge.source_file == "mypackage/calculator.py"
    assert calc_helper_edge.source_hash == _CALCULATOR_HASH
    assert calc_helper_edge.start_line <= 1  # import is on line 1
    assert calc_helper_edge.end_line >= 1


def test_external_vs_internal_import():
    """Test that external imports produce zero edges while internal produce valid edges."""
    from app.code_graph.models import SourceFile
    from app.code_graph.relationships import RelationshipExtractor

    external_content = "import requests"
    external_hash = "06185522e4085460db5f973d6987f2c5f42519fccd56836e5e5ed9842962de8d"

    external_files = [
        SourceFile(
            relative_path="external_module.py",
            language="python",
            content=external_content,
            content_hash=external_hash,
            byte_size=len(external_content.encode("utf-8")),
            line_count=1 if external_content else 0,
        ),
    ]

    external_decls = []

    # Extract relationships using an instantiated extractor
    extractor = RelationshipExtractor()
    result = extractor.extract(
        source_files=external_files,
        declarations=external_decls,
        repository_id="test-repo",
    )

    # External imports should produce zero IMPORTS edges
    import_edges = [e for e in result.edges if e.kind == EdgeKind.IMPORTS]
    assert len(import_edges) == 0, "External imports should not produce fabricated internal edges"