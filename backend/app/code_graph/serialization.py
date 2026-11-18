"""Phase 11.6 — deterministic graph serialization for the Code Graph.

This module is intentionally thin.  It reuses the Pydantic contracts from
``app.code_graph.models`` and the validation pass from
``app.code_graph.validation``; it never re-implements either.

Contracts
---------
* ``serialize_graph_json`` dumps ``CodeGraph.model_dump(mode="json")`` and
  canonicalizes it (NFC, sorted keys, compact separators).  The
  ``schema_version`` field from the model contract is preserved on output.
* ``deserialize_graph_json`` json-parses, gates on ``schema_version`` and
  materializes a ``CodeGraph``.  Parse/schema failures are reported as
  ``fatal`` diagnostics; a well-formed graph that fails the validation pass
  keeps the validation diagnostics and is rejected (``graph`` is ``None``).
  The two failure classes stay distinguishable via severity and codes.
* ``write_graph_file`` validates before serializing, writes to a temporary
  file in the destination directory and atomically replaces the target.
  An existing destination is only overwritten when it already parses as a
  KiteHut graph artifact; unrelated files are never clobbered.
* ``build_and_serialize`` is the end-to-end convenience: build, validate,
  write.  It never writes anywhere unless the caller passes ``output_path``.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from pydantic import ValidationError

from app.code_graph.models import (
    CODE_GRAPH_SCHEMA_VERSION,
    CodeGraph,
    DiagnosticSeverity,
    GraphBuildResult,
    GraphBuildStatus,
    GraphDiagnostic,
    GraphValidationResult,
    canonical_json,
)
from app.code_graph.validation import validate_graph

FATAL = DiagnosticSeverity.FATAL
ERROR = DiagnosticSeverity.ERROR


def _fatal_result(code: str, message: str) -> GraphValidationResult:
    return GraphValidationResult(
        valid=False,
        errors=[GraphDiagnostic(code=code, message=message, severity=FATAL)],
        checked_nodes=0,
        checked_edges=0,
    )


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


def _ordered_dump(graph: CodeGraph) -> Dict[str, Any]:
    data = graph.model_dump(mode="json")
    data["files"] = sorted(
        data["files"], key=lambda f: (f["relative_path"], f["id"])
    )
    data["symbols"] = sorted(
        data["symbols"],
        key=lambda s: (
            s["relative_path"],
            s["start_line"],
            s["start_column"] or 0,
            s["qualified_name"],
            s["id"],
        ),
    )
    data["edges"] = sorted(data["edges"], key=lambda e: e["id"])
    return data


def serialize_graph_json(graph: CodeGraph) -> str:
    """Return deterministic, canonical JSON bytes for ``graph``."""
    return canonical_json(_ordered_dump(graph))


# ---------------------------------------------------------------------------
# Deserialization
# ---------------------------------------------------------------------------


def deserialize_graph_json(
    json_text: str,
) -> Tuple[Optional[CodeGraph], GraphValidationResult]:
    """Load a graph from JSON and validate it.

    Returns ``(graph, validation_result)``.  A ``None`` graph means the
    artifact was rejected.  Parse/schema/contract failures carry ``fatal``
    diagnostics (``graph_parse_error`` / ``graph_schema_incompatible``);
    a contract-valid graph that fails the validation pass keeps the
    validator's own diagnostics (severity ``error``/``fatal`` as emitted).
    """
    try:
        payload = json.loads(json_text)
    except (json.JSONDecodeError, TypeError) as exc:
        return None, _fatal_result(
            "graph_parse_error", f"Graph JSON could not be parsed: {exc}"
        )
    if not isinstance(payload, dict):
        return None, _fatal_result(
            "graph_parse_error", "Graph JSON must contain a top-level object."
        )
    schema_version = payload.get("schema_version")
    if schema_version != CODE_GRAPH_SCHEMA_VERSION:
        return None, _fatal_result(
            "graph_schema_incompatible",
            f"Unsupported schema_version {schema_version!r}; "
            f"expected {CODE_GRAPH_SCHEMA_VERSION}.",
        )
    try:
        graph = CodeGraph.model_validate(payload)
    except ValidationError as exc:
        return None, _fatal_result(
            "graph_parse_error", f"Graph JSON does not satisfy the contract: {exc}"
        )

    result = validate_graph(graph)
    if not result.valid:
        return None, result
    return graph, result


# ---------------------------------------------------------------------------
# File output
# ---------------------------------------------------------------------------


def _looks_like_graph_artifact(path: Path) -> bool:
    try:
        payload = json.loads(path.read_bytes().decode("utf-8"))
    except Exception:
        return False
    return (
        isinstance(payload, dict)
        and payload.get("schema_version") == CODE_GRAPH_SCHEMA_VERSION
        and isinstance(payload.get("repository"), dict)
        and isinstance(payload.get("files"), list)
        and isinstance(payload.get("symbols"), list)
        and isinstance(payload.get("edges"), list)
    )


def write_graph_file(
    graph: CodeGraph,
    output_path: str | os.PathLike[str],
    *,
    validate: bool = True,
) -> Tuple[bool, List[GraphDiagnostic]]:
    """Serialize ``graph`` to ``output_path`` atomically.

    When ``validate`` is set (default), an invalid graph is rejected and no
    file is written.  An existing destination is overwritten only when it
    already parses as a KiteHut graph artifact; unrelated files are refused.
    Returns ``(success, diagnostics)``.
    """
    if validate:
        result = validate_graph(graph)
        if not result.valid:
            return False, list(result.errors)

    try:
        payload = serialize_graph_json(graph)
    except (ValueError, TypeError) as exc:
        return False, [
            GraphDiagnostic(
                code="graph_serialize_error",
                message=f"Graph could not be serialized: {exc}",
                severity=FATAL,
            )
        ]

    target = Path(output_path)
    if target.exists() and not _looks_like_graph_artifact(target):
        return False, [
            GraphDiagnostic(
                code="unrelated_file_exists",
                message=(
                    f"Refusing to overwrite existing file {str(target)!r}: it does "
                    "not parse as a KiteHut graph artifact."
                ),
                severity=FATAL,
            )
        ]

    tmp_name: Optional[str] = None
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=str(target.parent),
            prefix=target.name + ".", suffix=".tmp", delete=False,
        ) as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
            tmp_name = handle.name
        os.replace(tmp_name, str(target))
        tmp_name = None
        return True, []
    except OSError as exc:
        if tmp_name is not None:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
        return False, [
            GraphDiagnostic(
                code="graph_write_error",
                message=f"Graph could not be written to {str(target)!r}: {exc}",
                severity=FATAL,
            )
        ]


def build_and_serialize(
    builder,
    output_path: str | os.PathLike[str],
) -> Tuple[Optional[CodeGraph], GraphBuildResult]:
    """Build a graph with ``builder`` and serialize it to ``output_path``.

    The build already runs ``validate_graph``; an invalid or failed build
    returns ``(None, result)`` and writes nothing.  Only the caller-provided
    path is ever written.
    """
    result = builder.build()
    graph = result.graph
    if graph is None:
        return None, result

    success, diagnostics = write_graph_file(graph, output_path, validate=True)
    if success:
        return graph, result

    errors = [
        *result.errors,
        GraphDiagnostic(
            code="graph_output_failed",
            message="Graph build succeeded but serialization/write failed: "
            + "; ".join(d.message for d in diagnostics),
            severity=FATAL,
        ),
    ]
    failed = GraphBuildResult(
        graph=None,
        status=GraphBuildStatus.FAILED,
        coverage=result.coverage,
        truncated=result.truncated,
        errors=errors,
        warnings=result.warnings,
        unresolved_imports=result.unresolved_imports,
        unresolved_calls=result.unresolved_calls,
        file_count=0,
        symbol_count=0,
        edge_count=0,
    )
    return None, failed


__all__ = [
    "build_and_serialize",
    "deserialize_graph_json",
    "serialize_graph_json",
    "write_graph_file",
]
