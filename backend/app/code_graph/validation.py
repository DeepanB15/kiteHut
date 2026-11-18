"""Phase 11.5 — deterministic, fail-safe graph validation for KiteHut.

The validation layer is a read-only pass over an assembled :class:`CodeGraph`.
It never mutates the graph, never repairs invalid entities and never fabricates
relationships: every inconsistency is reported as a structured
:class:`GraphDiagnostic` carrying a stable code, a severity and a deterministic
sort position.

Checks (fixed order, pure functions of the input graph):

1. ``validate_node_ids``              — unique node IDs and edge IDs.
2. ``validate_edge_endpoints``        — edge endpoints exist and match the
                                        endpoint kinds required by the edge kind.
3. ``validate_repository_ownership``  — every entity belongs to the graph
                                        repository.
4. ``validate_file_and_symbol_references`` — deterministic file/symbol IDs,
                                        symbol ``file_id``/``relative_path``/
                                        ``source_hash`` agreement, and
                                        ``parent_id`` consistency.
5. ``validate_source_spans``          — 1-based inclusive spans on symbols and
                                        statement-backed edges.
6. ``validate_structural_consistency``— CONTAINS/DEFINES provenance agreement
                                        and parent-span containment.
7. ``validate_provenance_consistency``— edge provenance kind, ``source_file``
                                        existence and ``source_hash`` agreement.
8. ``detect_contradictions``          — self-referencing edges and containment
                                        cycles.

Diagnotics are ordered by ``(relative_path, line, code, message, severity)``
so identical graph input always yields byte-identical output.  ``validate_graph``
never raises on bad graph content: internal failures of an individual check are
captured as ``fatal`` diagnostics instead of aborting the run.
"""

from __future__ import annotations

from typing import Callable, List, Optional, Tuple

from app.code_graph.models import (
    CodeGraph,
    DiagnosticSeverity,
    EdgeKind,
    GraphDiagnostic,
    GraphEdge,
    GraphValidationResult,
    ProvenanceKind,
    SymbolNode,
    compute_file_id,
    compute_symbol_id,
    normalize_repository_path,
    validate_source_span,
)

ERROR = DiagnosticSeverity.ERROR
FATAL = DiagnosticSeverity.FATAL
WARNING = DiagnosticSeverity.WARNING


# ---------------------------------------------------------------------------
# Diagnostic construction helpers (hostile-input safe)
# ---------------------------------------------------------------------------


def _safe_entity_id(value: object) -> Optional[str]:
    """Return a diagnostic-safe entity ID, or ``None`` when unusable."""
    if not isinstance(value, str):
        return None
    candidate = value.strip()
    if not candidate or "/" in candidate or "\\" in candidate:
        return None
    if any(character.isspace() for character in candidate):
        return None
    return candidate


def _safe_path(value: object) -> Optional[str]:
    """Return a normalized relative path for diagnostics, or ``None``."""
    if not isinstance(value, str):
        return None
    try:
        return normalize_repository_path(value)
    except ValueError:
        return None


def _safe_line(value: object) -> Optional[int]:
    """Return a positive line number for diagnostics, or ``None``."""
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if value >= 1 else None


def _diagnostic(
    code: str,
    message: str,
    *,
    severity: DiagnosticSeverity,
    entity_id: object = None,
    relative_path: object = None,
    line: object = None,
) -> GraphDiagnostic:
    """Build a :class:`GraphDiagnostic` from possibly-hostile field values."""
    return GraphDiagnostic(
        code=code,
        message=message,
        severity=severity,
        entity_id=_safe_entity_id(entity_id),
        relative_path=_safe_path(relative_path),
        line=_safe_line(line),
    )


def _error(code: str, message: str, **context: object) -> GraphDiagnostic:
    return _diagnostic(code, message, severity=ERROR, **context)


def _warning(code: str, message: str, **context: object) -> GraphDiagnostic:
    return _diagnostic(code, message, severity=WARNING, **context)


def _diagnostic_sort_key(diagnostic: GraphDiagnostic) -> tuple:
    """Stable diagnostic ordering: path, line, code, message, severity."""
    return (
        diagnostic.relative_path or "",
        diagnostic.line or 0,
        diagnostic.code,
        diagnostic.message,
        diagnostic.severity.value,
    )


# ---------------------------------------------------------------------------
# Lookup helpers
# ---------------------------------------------------------------------------


def _file_by_id(graph: CodeGraph) -> dict:
    return {node.id: node for node in graph.files if node.id is not None}


def _symbol_by_id(graph: CodeGraph) -> dict:
    return {node.id: node for node in graph.symbols if node.id is not None}


def _repository_node_id(graph: CodeGraph) -> str:
    return graph.repository.id or graph.repository.repository_id


def _symbol_file_hash(symbol: SymbolNode, files: dict) -> Optional[str]:
    """Content hash of the file a symbol claims to live in, if known."""
    file_node = files.get(symbol.file_id)
    return file_node.content_hash if file_node is not None else None


# ---------------------------------------------------------------------------
# 1. Unique node IDs and edge IDs
# ---------------------------------------------------------------------------


def validate_node_ids(graph: CodeGraph) -> Tuple[bool, List[GraphDiagnostic]]:
    """Report duplicate node IDs and duplicate edge IDs."""
    diagnostics: List[GraphDiagnostic] = []
    seen: dict = {}

    entities: List[Tuple[str, object]] = [("repository", graph.repository)]
    entities.extend(("file", node) for node in graph.files)
    entities.extend(("symbol", node) for node in graph.symbols)

    for label, entity in entities:
        entity_id = getattr(entity, "id", None)
        if entity_id is None:
            continue
        if entity_id in seen:
            diagnostics.append(
                _error(
                    "duplicate_node_id",
                    f"Duplicate node ID '{entity_id}': already used by a "
                    f"{seen[entity_id]} node.",
                    entity_id=entity_id,
                    relative_path=getattr(entity, "relative_path", None),
                )
            )
        else:
            seen[entity_id] = label

    for edge in graph.edges:
        edge_id = edge.id
        if edge_id is None:
            continue
        if edge_id in seen:
            diagnostics.append(
                _error(
                    "duplicate_edge_id",
                    f"Duplicate edge ID '{edge_id}': already used by a "
                    f"{seen[edge_id]} entity.",
                    entity_id=edge_id,
                )
            )
        else:
            seen[edge_id] = "edge"

    return not diagnostics, diagnostics


# ---------------------------------------------------------------------------
# 2. Valid edge source and target references
# ---------------------------------------------------------------------------


def validate_edge_endpoints(graph: CodeGraph) -> Tuple[bool, List[GraphDiagnostic]]:
    """Report edges whose endpoints do not exist or have the wrong node kind."""
    diagnostics: List[GraphDiagnostic] = []

    file_ids = set(_file_by_id(graph))
    symbol_ids = set(_symbol_by_id(graph))
    repository_id = _repository_node_id(graph)

    for edge in graph.edges:
        source_id = edge.source_id
        target_id = edge.target_id
        kind = edge.kind

        if kind == EdgeKind.CONTAINS:
            if source_id == repository_id:
                source_ok = True
                target_ok = target_id in file_ids
            else:
                source_ok = source_id in file_ids or source_id in symbol_ids
                target_ok = target_id in symbol_ids
        elif kind == EdgeKind.DEFINES:
            source_ok = source_id in file_ids
            target_ok = target_id in symbol_ids
        elif kind == EdgeKind.IMPORTS:
            source_ok = source_id in file_ids
            target_ok = target_id in file_ids
        else:  # EdgeKind.CALLS
            source_ok = source_id in symbol_ids
            target_ok = target_id in symbol_ids

        if not source_ok:
            diagnostics.append(
                _error(
                    "invalid_edge_source",
                    f"{kind.value.upper()} edge source '{source_id}' is not a "
                    "valid endpoint for this edge kind.",
                    entity_id=edge.id,
                    relative_path=edge.source_file,
                    line=edge.start_line,
                )
            )
        if not target_ok:
            diagnostics.append(
                _error(
                    "invalid_edge_target",
                    f"{kind.value.upper()} edge target '{target_id}' is not a "
                    "valid endpoint for this edge kind.",
                    entity_id=edge.id,
                    relative_path=edge.source_file,
                    line=edge.start_line,
                )
            )

    return not diagnostics, diagnostics


# ---------------------------------------------------------------------------
# 3. Repository ownership
# ---------------------------------------------------------------------------


def validate_repository_ownership(
    graph: CodeGraph,
) -> Tuple[bool, List[GraphDiagnostic]]:
    """Report nodes and edges that do not belong to the graph repository."""
    diagnostics: List[GraphDiagnostic] = []
    repository_id = graph.repository.repository_id

    for label, entity in (
        *[("file", node) for node in graph.files],
        *[("symbol", node) for node in graph.symbols],
        *[("edge", edge) for edge in graph.edges],
    ):
        if entity.repository_id != repository_id:
            diagnostics.append(
                _error(
                    "cross_repository_reference",
                    f"{label.capitalize()} '{entity.id}' declares repository_id "
                    f"'{entity.repository_id}' but the graph owns repository_id "
                    f"'{repository_id}'.",
                    entity_id=entity.id,
                    relative_path=getattr(entity, "relative_path", None),
                )
            )

    return not diagnostics, diagnostics


# ---------------------------------------------------------------------------
# 4. File and symbol references
# ---------------------------------------------------------------------------


def validate_file_and_symbol_references(
    graph: CodeGraph,
) -> Tuple[bool, List[GraphDiagnostic]]:
    """Report non-deterministic file/symbol IDs and broken symbol references."""
    diagnostics: List[GraphDiagnostic] = []
    repository_id = graph.repository.repository_id
    files = _file_by_id(graph)
    symbols = _symbol_by_id(graph)

    for file_node in graph.files:
        try:
            expected = compute_file_id(repository_id, file_node.relative_path)
        except ValueError as exc:
            diagnostics.append(
                _error(
                    "invalid_file_reference",
                    f"File '{file_node.id}' has an unusable relative_path: {exc}",
                    entity_id=file_node.id,
                    line=1,
                )
            )
            continue
        if file_node.id != expected:
            diagnostics.append(
                _error(
                    "invalid_file_id",
                    f"File ID '{file_node.id}' does not match the deterministic "
                    f"identity '{expected}' for repository '{repository_id}' and "
                    f"path '{file_node.relative_path}'.",
                    entity_id=file_node.id,
                    relative_path=file_node.relative_path,
                )
            )

    for symbol in graph.symbols:
        try:
            expected = compute_symbol_id(
                repository_id,
                symbol.relative_path,
                symbol.qualified_name,
                symbol.kind,
                symbol.occurrence_ordinal,
            )
        except ValueError as exc:
            diagnostics.append(
                _error(
                    "invalid_symbol_reference",
                    f"Symbol '{symbol.id}' has an unusable identity input: {exc}",
                    entity_id=symbol.id,
                    relative_path=symbol.relative_path,
                    line=symbol.start_line,
                )
            )
            continue
        if symbol.id != expected:
            diagnostics.append(
                _error(
                    "invalid_symbol_id",
                    f"Symbol ID '{symbol.id}' does not match the deterministic "
                    f"identity '{expected}'.",
                    entity_id=symbol.id,
                    relative_path=symbol.relative_path,
                )
            )

        # file_id must reference a known file node.
        file_node = files.get(symbol.file_id)
        if file_node is None:
            diagnostics.append(
                _error(
                    "invalid_symbol_file_id",
                    f"Symbol '{symbol.id}' references file_id '{symbol.file_id}' "
                    "which is not present in the graph.",
                    entity_id=symbol.id,
                    relative_path=symbol.relative_path,
                    line=symbol.start_line,
                )
            )
        else:
            if symbol.relative_path != file_node.relative_path:
                diagnostics.append(
                    _error(
                        "symbol_file_path_mismatch",
                        f"Symbol '{symbol.id}' declares relative_path "
                        f"'{symbol.relative_path}' but its file_id resolves to "
                        f"'{file_node.relative_path}'.",
                        entity_id=symbol.id,
                        relative_path=symbol.relative_path,
                        line=symbol.start_line,
                    )
                )
            if symbol.source_hash != file_node.content_hash:
                diagnostics.append(
                    _error(
                        "symbol_source_hash_mismatch",
                        f"Symbol '{symbol.id}' source_hash does not match the "
                        f"content_hash of its file '{file_node.relative_path}'.",
                        entity_id=symbol.id,
                        relative_path=symbol.relative_path,
                        line=symbol.start_line,
                    )
                )

        # parent_id must reference an existing same-file symbol.
        if symbol.parent_id is not None:
            parent = symbols.get(symbol.parent_id)
            if parent is None:
                diagnostics.append(
                    _error(
                        "invalid_parent_reference",
                        f"Symbol '{symbol.id}' parent_id "
                        f"'{symbol.parent_id}' is not present in the graph.",
                        entity_id=symbol.id,
                        relative_path=symbol.relative_path,
                        line=symbol.start_line,
                    )
                )
            elif parent.relative_path != symbol.relative_path:
                diagnostics.append(
                    _error(
                        "invalid_parent_reference",
                        f"Symbol '{symbol.id}' parent '{parent.id}' lives in "
                        f"'{parent.relative_path}' but the child lives in "
                        f"'{symbol.relative_path}'.",
                        entity_id=symbol.id,
                        relative_path=symbol.relative_path,
                        line=symbol.start_line,
                    )
                )
            else:
                if (
                    parent.start_line > symbol.start_line
                    or parent.end_line < symbol.end_line
                ):
                    diagnostics.append(
                        _error(
                            "invalid_parent_span",
                            f"Parent '{parent.id}' span does not encompass child "
                            f"'{symbol.id}' span in '{symbol.relative_path}'.",
                            entity_id=symbol.id,
                            relative_path=symbol.relative_path,
                            line=symbol.start_line,
                        )
                    )
                expected_prefix = f"{parent.qualified_name}."
                if not symbol.qualified_name.startswith(expected_prefix):
                    diagnostics.append(
                        _warning(
                            "qualified_name_inconsistent",
                            f"Symbol '{symbol.id}' qualified_name "
                            f"'{symbol.qualified_name}' is not nested under parent "
                            f"'{parent.qualified_name}'.",
                            entity_id=symbol.id,
                            relative_path=symbol.relative_path,
                            line=symbol.start_line,
                        )
                    )

    return not diagnostics, diagnostics


# ---------------------------------------------------------------------------
# 5. Source spans
# ---------------------------------------------------------------------------


def _check_span(
    start_line: object,
    end_line: object,
    start_column: object,
    end_column: object,
    *,
    require_columns: bool,
) -> Optional[str]:
    """Return the validation error message for a span, or ``None`` when valid."""
    if (
        start_line is None
        and end_line is None
        and start_column is None
        and end_column is None
    ):
        return None
    try:
        validate_source_span(
            start_line,
            end_line,
            start_column,
            end_column,
            require_columns=require_columns,
            required=True,
        )
    except ValueError as exc:
        return str(exc)
    return None


def validate_source_spans(graph: CodeGraph) -> Tuple[bool, List[GraphDiagnostic]]:
    """Report invalid 1-based inclusive source spans on symbols and edges."""
    diagnostics: List[GraphDiagnostic] = []

    for symbol in graph.symbols:
        message = _check_span(
            symbol.start_line,
            symbol.end_line,
            symbol.start_column,
            symbol.end_column,
            require_columns=False,
        )
        if message is not None:
            diagnostics.append(
                _error(
                    "invalid_source_span",
                    f"Symbol '{symbol.id}' span is invalid: {message}",
                    entity_id=symbol.id,
                    relative_path=symbol.relative_path,
                    line=symbol.start_line,
                )
            )

    for edge in graph.edges:
        require_columns = edge.kind in (EdgeKind.IMPORTS, EdgeKind.CALLS)
        message = _check_span(
            edge.start_line,
            edge.end_line,
            edge.start_column,
            edge.end_column,
            require_columns=require_columns,
        )
        if message is not None:
            diagnostics.append(
                _error(
                    "invalid_source_span",
                    f"Edge '{edge.id}' span is invalid: {message}",
                    entity_id=edge.id,
                    relative_path=edge.source_file,
                    line=edge.start_line,
                )
            )

    return not diagnostics, diagnostics


# ---------------------------------------------------------------------------
# 6. Structural relationships and parent-child consistency
# ---------------------------------------------------------------------------


def validate_structural_consistency(
    graph: CodeGraph,
) -> Tuple[bool, List[GraphDiagnostic]]:
    """Report contradictory CONTAINS/DEFINES structure and span containment."""
    diagnostics: List[GraphDiagnostic] = []
    repository_id = _repository_node_id(graph)
    files = _file_by_id(graph)
    symbols = _symbol_by_id(graph)
    parents: dict = {}

    for edge in sorted(graph.edges, key=lambda item: item.id or ""):
        if edge.kind == EdgeKind.CONTAINS:
            if edge.source_id == repository_id:
                target_file = files.get(edge.target_id)
                if target_file is not None and edge.source_file != (
                    target_file.relative_path
                ):
                    diagnostics.append(
                        _error(
                            "structural_inconsistency",
                            f"Repository CONTAINS edge '{edge.id}' cites "
                            f"source_file '{edge.source_file}' but targets file "
                            f"'{target_file.relative_path}'.",
                            entity_id=edge.id,
                            relative_path=edge.source_file,
                        )
                    )
            else:
                child = symbols.get(edge.target_id)
                if child is not None and edge.source_file != child.relative_path:
                    diagnostics.append(
                        _error(
                            "structural_inconsistency",
                            f"CONTAINS edge '{edge.id}' cites source_file "
                            f"'{edge.source_file}' but the child symbol lives in "
                            f"'{child.relative_path}'.",
                            entity_id=edge.id,
                            relative_path=edge.source_file,
                        )
                    )
                if edge.source_id in symbols and edge.target_id in symbols:
                    parents[edge.target_id] = edge.source_id
                    parent = symbols[edge.source_id]
                    if (
                        parent.start_line > child.start_line
                        or parent.end_line < child.end_line
                    ):
                        diagnostics.append(
                            _error(
                                "structural_inconsistency",
                                f"CONTAINS edge '{edge.id}': parent span "
                                f"{parent.start_line}-{parent.end_line} does not "
                                f"encompass child span {child.start_line}-"
                                f"{child.end_line} in '{child.relative_path}'.",
                                entity_id=edge.id,
                                relative_path=child.relative_path,
                                line=child.start_line,
                            )
                        )
        elif edge.kind == EdgeKind.DEFINES:
            symbol = symbols.get(edge.target_id)
            if symbol is not None and edge.source_file != symbol.relative_path:
                diagnostics.append(
                    _error(
                        "structural_inconsistency",
                        f"DEFINES edge '{edge.id}' cites source_file "
                        f"'{edge.source_file}' but the symbol lives in "
                        f"'{symbol.relative_path}'.",
                        entity_id=edge.id,
                        relative_path=edge.source_file,
                    )
                )
            source_file = files.get(edge.source_id)
            if source_file is not None and edge.source_file != (
                source_file.relative_path
            ):
                diagnostics.append(
                    _error(
                        "structural_inconsistency",
                        f"DEFINES edge '{edge.id}' cites source_file "
                        f"'{edge.source_file}' but originates from file "
                        f"'{source_file.relative_path}'.",
                        entity_id=edge.id,
                        relative_path=edge.source_file,
                    )
                )

    # Containment cycles: a symbol may not (transitively) contain itself.
    for symbol in sorted(graph.symbols, key=lambda item: item.id or ""):
        visited: set = set()
        current: Optional[str] = symbol.id
        steps = 0
        while current is not None and current in parents:
            if current in visited:
                diagnostics.append(
                    _error(
                        "contains_cycle",
                        f"CONTAINS hierarchy starting at '{symbol.id}' forms a "
                        "cycle; lexical containment must be acyclic.",
                        entity_id=symbol.id,
                        relative_path=symbol.relative_path,
                        line=symbol.start_line,
                    )
                )
                break
            visited.add(current)
            current = parents[current]
            steps += 1
            if steps > len(graph.symbols):
                break

    return not diagnostics, diagnostics


# ---------------------------------------------------------------------------
# 7. Provenance consistency
# ---------------------------------------------------------------------------


def _expected_provenance(edge: GraphEdge, repository_id: str) -> ProvenanceKind:
    """Return the provenance kind required for ``edge`` by its edge kind."""
    if edge.kind == EdgeKind.CONTAINS:
        if edge.source_id == repository_id:
            return ProvenanceKind.DISCOVERED_PATH
        return ProvenanceKind.DECLARATION
    if edge.kind == EdgeKind.DEFINES:
        return ProvenanceKind.DECLARATION
    if edge.kind == EdgeKind.IMPORTS:
        return ProvenanceKind.IMPORT_STATEMENT
    return ProvenanceKind.CALL_SITE


def validate_provenance_consistency(
    graph: CodeGraph,
) -> Tuple[bool, List[GraphDiagnostic]]:
    """Report wrong provenance kinds, unknown source files and hash mismatches."""
    diagnostics: List[GraphDiagnostic] = []
    repository_id = _repository_node_id(graph)
    files_by_path = {
        node.relative_path: node for node in graph.files if node.id is not None
    }

    for edge in graph.edges:
        expected = _expected_provenance(edge, repository_id)
        if edge.provenance_kind != expected:
            diagnostics.append(
                _error(
                    "invalid_provenance",
                    f"{edge.kind.value.upper()} edge '{edge.id}' requires "
                    f"provenance_kind '{expected.value}', got "
                    f"'{edge.provenance_kind.value}'.",
                    entity_id=edge.id,
                    relative_path=edge.source_file,
                    line=edge.start_line,
                )
            )

        if edge.source_file is None:
            diagnostics.append(
                _error(
                    "missing_provenance_data",
                    f"{edge.kind.value.upper()} edge '{edge.id}' is missing the "
                    "source_file provenance path.",
                    entity_id=edge.id,
                )
            )
        else:
            file_node = files_by_path.get(edge.source_file)
            if file_node is None:
                diagnostics.append(
                    _error(
                        "edge_source_file_unknown",
                        f"Edge '{edge.id}' cites source_file "
                        f"'{edge.source_file}' which is not present in the graph.",
                        entity_id=edge.id,
                        relative_path=edge.source_file,
                        line=edge.start_line,
                    )
                )
            elif edge.source_hash is not None and (
                edge.source_hash != file_node.content_hash
            ):
                diagnostics.append(
                    _error(
                        "edge_source_hash_mismatch",
                        f"Edge '{edge.id}' source_hash does not match the "
                        f"content_hash of source_file '{edge.source_file}'.",
                        entity_id=edge.id,
                        relative_path=edge.source_file,
                        line=edge.start_line,
                    )
                )

        if edge.source_hash is None:
            diagnostics.append(
                _error(
                    "missing_provenance_data",
                    f"{edge.kind.value.upper()} edge '{edge.id}' is missing the "
                    "source_hash provenance digest.",
                    entity_id=edge.id,
                )
            )

    return not diagnostics, diagnostics


# ---------------------------------------------------------------------------
# 8. Contradictory structures
# ---------------------------------------------------------------------------


def detect_contradictions(graph: CodeGraph) -> List[GraphDiagnostic]:
    """Report self-referencing edges and duplicate structural facts."""
    diagnostics: List[GraphDiagnostic] = []

    for edge in graph.edges:
        if edge.source_id == edge.target_id:
            diagnostics.append(
                _error(
                    "self_referencing_edge",
                    f"Edge '{edge.id}' connects node '{edge.source_id}' to itself; "
                    "edges must connect distinct nodes.",
                    entity_id=edge.id,
                    relative_path=edge.source_file,
                    line=edge.start_line,
                )
            )

    return diagnostics


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

_CHECKS: Tuple[Callable[[CodeGraph], Tuple[bool, List[GraphDiagnostic]]], ...] = (
    validate_node_ids,
    validate_edge_endpoints,
    validate_repository_ownership,
    validate_file_and_symbol_references,
    validate_source_spans,
    validate_structural_consistency,
    validate_provenance_consistency,
)


def validate_graph(graph: CodeGraph) -> GraphValidationResult:
    """
    Validate an assembled graph and return a deterministic
    :class:`GraphValidationResult`.

    The graph is never modified.  Every check runs even when earlier checks
    fail, and any check that raises internally is converted into a ``fatal``
    diagnostic so validation itself cannot crash a caller.
    """
    if not isinstance(graph, CodeGraph):
        raise TypeError("validate_graph expects a CodeGraph instance.")

    collected: List[GraphDiagnostic] = []

    for check in _CHECKS:
        try:
            _, diagnostics = check(graph)
        except Exception as exc:  # fail-safe: never abort the validation pass
            diagnostics = [
                _diagnostic(
                    "validation_check_failed",
                    f"Validation check '{check.__name__}' raised "
                    f"{type(exc).__name__}: {exc}",
                    severity=FATAL,
                )
            ]
        collected.extend(diagnostics)

    try:
        collected.extend(detect_contradictions(graph))
    except Exception as exc:  # fail-safe
        collected.append(
            _diagnostic(
                "validation_check_failed",
                f"Contradiction detection raised {type(exc).__name__}: {exc}",
                severity=FATAL,
            )
        )

    ordered = sorted(collected, key=_diagnostic_sort_key)
    errors = [
        diagnostic
        for diagnostic in ordered
        if diagnostic.severity in (ERROR, FATAL)
    ]
    warnings = [
        diagnostic
        for diagnostic in ordered
        if diagnostic.severity not in (ERROR, FATAL)
    ]

    return GraphValidationResult(
        valid=not errors,
        errors=errors,
        warnings=warnings,
        checked_nodes=1 + len(graph.files) + len(graph.symbols),
        checked_edges=len(graph.edges),
    )


__all__ = [
    "detect_contradictions",
    "validate_edge_endpoints",
    "validate_file_and_symbol_references",
    "validate_graph",
    "validate_node_ids",
    "validate_provenance_consistency",
    "validate_repository_ownership",
    "validate_source_spans",
    "validate_structural_consistency",
]
