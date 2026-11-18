"""Phase 11.6 — deterministic CodeGraphBuilder.

The builder composes the earlier Phase 11 tasks into one reproducible
pipeline:

    discover -> extract -> resolve relationships -> assemble graph
    -> validate -> GraphBuildResult

It never mutates the source repository, starts services, calls Ollama, or
persists anything to a database.  Every failure state is surfaced through the
returned :class:`GraphBuildResult`:

* ``complete`` — exhaustive discovery and successful processing of every
  in-scope supported file, with zero validation errors.
* ``partial``  — a usable graph is retained despite a syntax error, an
  unreadable in-scope file, or file-limit truncation.
* ``failed``   — invalid/missing root, fatal scan failure, or validation
  errors; no graph is returned.

Unsupported-language files stay listed in per-language coverage and are never
represented as semantically analyzed.  Unresolved/ambiguous relationship
diagnostics alone do not downgrade a build.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from app.code_graph.discovery import RepositoryScanner
from app.code_graph.models import (
    CodeGraph,
    DiagnosticSeverity,
    FileNode,
    GraphBuildResult,
    GraphBuildStatus,
    GraphDiagnostic,
    GraphEdge,
    GraphValidationResult,
    LanguageCoverage,
    RepositoryNode,
    SourceFile,
    SymbolDeclaration,
    SymbolNode,
)
from app.code_graph.python_extractor import PythonASTExtractor
from app.code_graph.relationships import RelationshipExtractor
from app.code_graph.validation import validate_graph

PYTHON_LANGUAGE = "python"
EXTRACTOR_NAME = "python_ast"


def _diagnostic(
    code: str,
    message: str,
    *,
    severity: DiagnosticSeverity,
    relative_path: Optional[str] = None,
    line: Optional[int] = None,
) -> GraphDiagnostic:
    return GraphDiagnostic(
        code=code,
        message=message,
        severity=severity,
        relative_path=relative_path,
        line=line,
    )


def _diagnostic_sort_key(diagnostic: GraphDiagnostic) -> tuple:
    return (
        diagnostic.relative_path or "",
        diagnostic.line or 0,
        diagnostic.code,
        diagnostic.message,
        diagnostic.severity.value,
    )


class CodeGraphBuilder:
    """Assemble a validated :class:`CodeGraph` from a repository root."""

    def __init__(
        self,
        root_path: str | Path,
        repository_id: Optional[str] = None,
        scanner: Optional[RepositoryScanner] = None,
    ) -> None:
        if scanner is not None and not isinstance(scanner, RepositoryScanner):
            raise TypeError("scanner must be a RepositoryScanner instance.")
        self.root_path = root_path
        self.repository_id = repository_id
        self.scanner = scanner or RepositoryScanner(
            root_path, repository_id=repository_id
        )
        self.extractor = PythonASTExtractor()
        self.relationship_extractor = RelationshipExtractor()

    def build(self) -> GraphBuildResult:
        """Run the full pipeline and return a :class:`GraphBuildResult`."""
        # 1. Discover --------------------------------------------------------
        scan = self.scanner.scan()
        if scan.status == GraphBuildStatus.FAILED:
            return scan

        # Discovery-level diagnostics (unreadable/decode-failed files, file
        # limit warnings) carry the scan's authoritative view of the tree;
        # the builder layers its own extraction diagnostics on top instead of
        # replacing them.
        processing_errors: list[GraphDiagnostic] = list(scan.errors)
        source_files = self.scanner.source_files
        repository_node = scan.graph.repository
        repository_id = repository_node.repository_id
        source_digest = scan.graph.source_digest
        file_nodes = list(scan.graph.files)

        # 2. Extract ---------------------------------------------------------
        declarations: list[SymbolDeclaration] = []
        syntax_error_files: set[str] = set()
        unreadable_files: set[str] = set()

        for source_file in source_files:
            try:
                found = self.extractor.extract(source_file)
            except SyntaxError as exc:
                syntax_error_files.add(source_file.relative_path)
                processing_errors.append(
                    _diagnostic(
                        "syntax_error",
                        f"Syntax error in {source_file.relative_path}: "
                        f"{exc.msg} (line {exc.lineno}, offset {exc.offset})",
                        severity=DiagnosticSeverity.ERROR,
                        relative_path=source_file.relative_path,
                        line=getattr(exc, "lineno", None),
                    )
                )
            except OSError as exc:
                unreadable_files.add(source_file.relative_path)
                processing_errors.append(
                    _diagnostic(
                        "file_unreadable",
                        f"File '{source_file.relative_path}' could not be read: "
                        f"{exc}",
                        severity=DiagnosticSeverity.ERROR,
                        relative_path=source_file.relative_path,
                    )
                )
            else:
                declarations.extend(found)

        # 3. Resolve relationships -------------------------------------------
        try:
            relationship = self.relationship_extractor.extract(
                source_files, declarations, repository_id
            )
        except Exception as exc:  # fail-safe: surface, never crash the build
            return GraphBuildResult(
                graph=None,
                status=GraphBuildStatus.FAILED,
                errors=[
                    _diagnostic(
                        "relationship_extraction_failed",
                        f"Relationship extraction raised "
                        f"{type(exc).__name__}: {exc}",
                        severity=DiagnosticSeverity.FATAL,
                    )
                ],
                file_count=len(file_nodes),
                symbol_count=len(declarations),
            )

        # 4. Assemble graph ---------------------------------------------------
        try:
            graph = self._assemble(
                repository_node,
                file_nodes,
                source_files,
                declarations,
                relationship.edges,
                source_digest,
            )
        except ValueError as exc:
            return GraphBuildResult(
                graph=None,
                status=GraphBuildStatus.FAILED,
                errors=[
                    _diagnostic(
                        "graph_assembly_failed",
                        f"Could not assemble the code graph: {exc}",
                        severity=DiagnosticSeverity.FATAL,
                    )
                ],
                file_count=len(file_nodes),
                symbol_count=len(declarations),
                edge_count=len(relationship.edges),
            )

        # 5. Validate ---------------------------------------------------------
        validation: GraphValidationResult = validate_graph(graph)

        warnings: list[GraphDiagnostic] = [
            *scan.warnings,
            *validation.warnings,
        ]
        warnings.sort(key=_diagnostic_sort_key)

        # A validator error rejects the graph entirely: the build fails and
        # carries no graph rather than handing back known-defective output.
        if validation.errors:
            fatal_errors = [
                error
                for error in validation.errors
                if error.severity == DiagnosticSeverity.FATAL
            ]
            errors = [
                _diagnostic(
                    "graph_validation_failed",
                    f"Graph validation reported {len(validation.errors)} "
                    "error(s); the build was rejected.",
                    severity=DiagnosticSeverity.FATAL,
                ),
                *fatal_errors,
                *[
                    error
                    for error in validation.errors
                    if error.severity != DiagnosticSeverity.FATAL
                ],
            ]
            errors.sort(key=_diagnostic_sort_key)
            return GraphBuildResult(
                graph=None,
                status=GraphBuildStatus.FAILED,
                coverage=self._coverage(
                    scan, source_files, syntax_error_files, unreadable_files
                ),
                truncated=scan.truncated,
                errors=errors,
                warnings=warnings,
                unresolved_imports=relationship.unresolved_imports,
                unresolved_calls=relationship.unresolved_calls,
                file_count=len(file_nodes),
                symbol_count=len(graph.symbols),
                edge_count=len(graph.edges),
            )

        # 6. Coverage and status ----------------------------------------------
        coverage = self._coverage(
            scan, source_files, syntax_error_files, unreadable_files
        )
        truncated = scan.truncated
        processing_errors.sort(key=_diagnostic_sort_key)

        coverage_gap = any(
            entry.supported
            and (
                entry.analyzed_files != entry.discovered_files
                or entry.skipped_files != 0
            )
            for entry in coverage
        )

        if processing_errors or truncated or coverage_gap:
            status = GraphBuildStatus.PARTIAL
        else:
            status = GraphBuildStatus.COMPLETE

        return GraphBuildResult(
            graph=graph,
            status=status,
            coverage=coverage,
            truncated=truncated,
            errors=processing_errors,
            warnings=warnings,
            unresolved_imports=relationship.unresolved_imports,
            unresolved_calls=relationship.unresolved_calls,
            file_count=len(graph.files),
            symbol_count=len(graph.symbols),
            edge_count=len(graph.edges),
        )

    # -- internals -----------------------------------------------------------

    def _assemble(
        self,
        repository: RepositoryNode,
        file_nodes: list[FileNode],
        source_files: list[SourceFile],
        declarations: list[SymbolDeclaration],
        edges: list[GraphEdge],
        source_digest: Optional[str],
    ) -> CodeGraph:
        repository_id = repository.repository_id

        hash_by_path = {
            source_file.relative_path: source_file.content_hash
            for source_file in source_files
        }
        file_id_by_path = {
            file_node.relative_path: file_node.id for file_node in file_nodes
        }

        symbol_nodes: list[SymbolNode] = []
        for declaration in declarations:
            file_id = file_id_by_path.get(declaration.relative_path)
            if file_id is None:
                raise ValueError(
                    f"Declaration '{declaration.qualified_name}' references file "
                    f"'{declaration.relative_path}' which is not in the graph."
                )
            content_hash = hash_by_path.get(declaration.relative_path)
            if content_hash is None:
                raise ValueError(
                    f"Declaration '{declaration.qualified_name}' has no discovered "
                    f"file content hash for '{declaration.relative_path}'."
                )
            symbol_nodes.append(
                SymbolNode(
                    repository_id=repository_id,
                    file_id=file_id,
                    relative_path=declaration.relative_path,
                    name=declaration.name,
                    qualified_name=declaration.qualified_name,
                    kind=declaration.kind,
                    parent_id=None,
                    start_line=declaration.start_line,
                    end_line=declaration.end_line,
                    start_column=declaration.start_column,
                    end_column=declaration.end_column,
                    source_hash=content_hash,
                    extractor=EXTRACTOR_NAME,
                    occurrence_ordinal=declaration.occurrence_ordinal,
                )
            )

        symbol_id_by_qualified_name = {
            symbol.qualified_name: symbol.id for symbol in symbol_nodes
        }
        declaration_by_qualified_name = {
            declaration.qualified_name: declaration
            for declaration in declarations
        }
        for symbol in symbol_nodes:
            declaration = declaration_by_qualified_name.get(symbol.qualified_name)
            if declaration is None or declaration.parent_qualified_name is None:
                continue
            parent_id = symbol_id_by_qualified_name.get(
                declaration.parent_qualified_name
            )
            if parent_id is not None:
                symbol.parent_id = parent_id

        # Edges carry deterministic IDs from construction; dedupe defensively
        # in case relationship extraction emitted a duplicate.  The assembled
        # order is the canonical id order so build output and canonical JSON
        # serialization agree byte-for-byte on edge ordering.
        seen_edge_ids: set[str] = set()
        ordered_edges: list[GraphEdge] = []
        for edge in edges:
            if edge.id in seen_edge_ids:
                continue
            seen_edge_ids.add(edge.id)
            ordered_edges.append(edge)
        ordered_edges.sort(key=lambda edge: edge.id)

        return CodeGraph(
            repository=repository,
            files=list(file_nodes),
            symbols=symbol_nodes,
            edges=ordered_edges,
            source_digest=source_digest,
        )

    def _coverage(
        self,
        scan: GraphBuildResult,
        source_files: list[SourceFile],
        syntax_error_files: set[str],
        unreadable_files: set[str],
    ) -> list:
        python_files = [
            sf for sf in source_files
            if sf.language.lower() == PYTHON_LANGUAGE
        ]
        analyzed = len(python_files) - len(syntax_error_files) - len(
            unreadable_files
        )
        skipped = len(syntax_error_files) + len(unreadable_files)

        coverage = [
            LanguageCoverage(
                language=PYTHON_LANGUAGE,
                supported=True,
                discovered_files=len(python_files),
                analyzed_files=analyzed,
                skipped_files=skipped,
            )
        ]
        for entry in scan.coverage:
            if entry.language.lower() == PYTHON_LANGUAGE:
                continue
            coverage.append(entry)
        coverage.sort(key=lambda item: item.language)
        return coverage


__all__ = ["CodeGraphBuilder"]
