"""Phase 11.11 — read-only Code Graph, Smart Context and Evidence tools.

These tools extend the existing tool registry (and therefore the existing agent
executor and MCP server).  They are deliberately thin adapters:

* graph queries use ``app.code_graph.queries`` (no second traversal engine),
* graph-guided retrieval uses ``integrate_graph_into_retrieval`` (Phase 11.9),
* claim verification uses ``verify_claim_with_graph`` (Phase 11.10) and the
  existing Phase 7 verifiers.

Every tool is read-only, returns a deterministic JSON document as its output,
bounds traversal depth and result count, and degrades to a structured
"graph unavailable" payload instead of raising when graph data is missing.

Graph relationships are static navigation evidence.  Nothing in this module
claims runtime behaviour or impact.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from app.agent.permissions.policies import PermissionType, RiskLevel
from app.code_graph import (
    CODE_GRAPH_SCHEMA_VERSION,
    CodeGraphBuilder,
    GraphBuildStatus,
    SymbolNode,
    callees,
    callers,
    dependents,
    find_symbols,
    imports,
    normalize_repository_path,
)
from app.code_graph.evidence import verify_claim_with_graph
from app.code_graph.integration import integrate_graph_into_retrieval
from app.code_graph.models import CodeGraph, FileNode, GraphBuildResult
from app.chunking.repository_chunker import chunk_repo
from app.tools.base import BaseTool
from app.tools.sandbox import PathValidator, SecurityViolationError
from app.verification.models.claim import ClaimType, ExtractedClaim

DEFAULT_LIMIT = 20
MAX_LIMIT = 50
DEFAULT_DEPTH = 1
MAX_DEPTH = 3
MAX_CONTEXT_FILES = 200
MAX_CONTEXT_CHUNKS = 1500
MAX_GRAPH_DIAGNOSTICS = 5

NAVIGATION_DISCLAIMER = (
    "Code Graph relationships are static navigation evidence, not proof of "
    "runtime behaviour or guaranteed execution paths."
)

REPOSITORY_SCHEMA = {
    "type": "string",
    "description": "Root workspace repository path (selected by the caller).",
}

LIMIT_SCHEMA = {
    "type": "integer",
    "description": f"Maximum results (default {DEFAULT_LIMIT}, max {MAX_LIMIT}).",
}

DEPTH_SCHEMA = {
    "type": "integer",
    "description": f"Traversal depth (default {DEFAULT_DEPTH}, max {MAX_DEPTH}).",
}


# ---------------------------------------------------------------------------
# Repository and graph access
# ---------------------------------------------------------------------------


def _resolve_repository_root(repository_path: str) -> Path:
    """Resolve and validate the selected workspace root.

    Rejects empty input, non-directories and filesystem anchors.  A bare drive
    root (or ``/``) is never a valid repository workspace.
    """
    if not isinstance(repository_path, str) or not repository_path.strip():
        raise ValueError("repository_path must be a non-empty string.")

    candidate = Path(repository_path).expanduser()
    root = (Path.cwd() / candidate).resolve() if not candidate.is_absolute() else candidate.resolve()

    if not root.exists():
        raise FileNotFoundError(f"Repository path does not exist: {repository_path}")
    if not root.is_dir():
        raise NotADirectoryError(f"Repository path is not a directory: {repository_path}")
    if root.parent == root:
        raise SecurityViolationError(
            "A filesystem root is not a valid repository workspace."
        )
    return root


def _bounded_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def _contained_relative_path(raw_path: str, root: Path) -> str:
    """Resolve a caller-supplied path and return its repository-relative form.

    Reuses the existing ``PathValidator`` containment guard, which resolves
    symlinks and rejects traversal and absolute escapes outside the workspace.
    """
    resolved = PathValidator.resolve_safe_path(raw_path, str(root))
    try:
        relative = resolved.relative_to(root)
    except ValueError as error:  # pragma: no cover - defensive, guard already checks
        raise SecurityViolationError(
            f"Path traversal detected: '{raw_path}' is outside repository '{root}'"
        ) from error
    return normalize_repository_path(relative.as_posix())


def _clamp_text(value: Any, name: str, *, required: bool = False) -> Optional[str]:
    if value is None:
        if required:
            raise ValueError(f"{name} is required.")
        return None
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a string.")
    stripped = value.strip()
    if not stripped:
        if required:
            raise ValueError(f"{name} must not be empty.")
        return None
    return stripped


@dataclass
class _GraphAccess:
    """Outcome of loading a graph for one tool invocation."""

    root: Path
    result: Optional[GraphBuildResult]
    graph: Optional[CodeGraph]
    error: Optional[str] = None


def _load_graph(root: Path) -> _GraphAccess:
    """Build a validated graph for ``root``; never raise to the tool caller."""
    try:
        result = CodeGraphBuilder(root).build()
    except Exception as error:  # graph building must never crash the agent
        return _GraphAccess(root=root, result=None, graph=None, error=str(error))

    graph = result.graph
    if result.status == GraphBuildStatus.FAILED or graph is None:
        return _GraphAccess(
            root=root,
            result=result,
            graph=None,
            error="Code Graph build failed for this repository.",
        )
    if graph.schema_version != CODE_GRAPH_SCHEMA_VERSION:
        return _GraphAccess(
            root=root,
            result=result,
            graph=None,
            error=(
                f"Code Graph schema {graph.schema_version} is not supported "
                f"(expected {CODE_GRAPH_SCHEMA_VERSION})."
            ),
        )
    return _GraphAccess(root=root, result=result, graph=graph)


def _graph_payload(access: _GraphAccess) -> Dict[str, Any]:
    """Compact, deterministic graph availability/provenance description."""
    result = access.result
    graph = access.graph
    payload: Dict[str, Any] = {
        "available": graph is not None,
        "valid": graph is not None,
        "status": result.status.value if result is not None else "failed",
        "truncated": bool(result.truncated) if result is not None else False,
        "schema_version": getattr(graph, "schema_version", None),
        "repository_id": (
            graph.repository.repository_id if graph is not None else None
        ),
        "counts": {
            "files": result.file_count if result is not None else 0,
            "symbols": result.symbol_count if result is not None else 0,
            "edges": result.edge_count if result is not None else 0,
        },
        "unresolved": {
            "imports": len(result.unresolved_imports) if result is not None else 0,
            "calls": len(result.unresolved_calls) if result is not None else 0,
        },
        "error": access.error,
    }
    if result is not None:
        payload["errors"] = [d.message for d in result.errors[:MAX_GRAPH_DIAGNOSTICS]]
        payload["warnings"] = [d.message for d in result.warnings[:MAX_GRAPH_DIAGNOSTICS]]
    return payload


def _json_output(payload: Dict[str, Any]) -> str:
    """Serialize tool output deterministically (no timestamps, sorted keys)."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


# ---------------------------------------------------------------------------
# Node payloads
# ---------------------------------------------------------------------------


def _symbol_payload(symbol: Optional[SymbolNode], symbol_id: str) -> Dict[str, Any]:
    if symbol is None:
        return {"symbol_id": symbol_id, "resolved": False}
    return {
        "resolved": True,
        "symbol_id": symbol.id,
        "name": symbol.name,
        "qualified_name": symbol.qualified_name,
        "kind": symbol.kind.value,
        "relative_path": symbol.relative_path,
        "file_id": symbol.file_id,
        "parent_id": symbol.parent_id,
        "start_line": symbol.start_line,
        "end_line": symbol.end_line,
        "start_column": symbol.start_column,
        "end_column": symbol.end_column,
        "source_hash": symbol.source_hash,
    }


def _file_payload(file_node: Optional[FileNode], file_id: str) -> Dict[str, Any]:
    if file_node is None:
        return {"file_id": file_id, "resolved": False}
    return {
        "resolved": True,
        "file_id": file_node.id,
        "relative_path": file_node.relative_path,
        "language": file_node.language,
        "content_hash": file_node.content_hash,
        "line_count": file_node.line_count,
    }


def _node_index(graph: CodeGraph) -> Tuple[Dict[str, SymbolNode], Dict[str, FileNode]]:
    return (
        {symbol.id: symbol for symbol in graph.symbols},
        {file.id: file for file in graph.files},
    )


def _resolve_symbol(
    graph: CodeGraph, query: str
) -> Tuple[List[SymbolNode], str]:
    """Resolve a symbol by canonical ID, exact name/qualified name, or partial."""
    if query.startswith("symbol:v1:"):
        matches = [symbol for symbol in graph.symbols if symbol.id == query]
        return matches, "symbol_id"

    exact = [
        symbol
        for symbol in graph.symbols
        if symbol.name == query or symbol.qualified_name == query
    ]
    if exact:
        return sorted(exact, key=lambda symbol: symbol.id or ""), "exact"

    partial = find_symbols(graph, query)
    return partial, "partial"


def _symbol_candidates(matches: Sequence[SymbolNode], limit: int) -> List[Dict[str, Any]]:
    return [_symbol_payload(symbol, symbol.id or "") for symbol in matches[:limit]]


def _relationship_entry(
    *,
    direction: str,
    node: Dict[str, Any],
    hit: Any,
    depth: int,
) -> Dict[str, Any]:
    provenance = hit.provenance()
    provenance["edge_id"] = hit.edge.id
    provenance["edge_kind"] = hit.edge.kind.value
    return {
        "direction": direction,
        "depth": depth,
        "node": node,
        "edge": provenance,
    }


class _SymbolQueryTool(BaseTool):
    """Shared implementation for caller/callee/impact symbol traversal."""

    permission_type = PermissionType.READ
    risk_level = RiskLevel.SAFE
    relationship: str = "callers"

    def get_parameter_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": (
                        "Symbol name, qualified name, or canonical symbol:v1:... ID."
                    ),
                },
                "depth": DEPTH_SCHEMA,
                "limit": LIMIT_SCHEMA,
                "repository_path": REPOSITORY_SCHEMA,
            },
            "required": ["symbol", "repository_path"],
        }

    def run(
        self,
        symbol: str,
        repository_path: str,
        depth: int = DEFAULT_DEPTH,
        limit: int = DEFAULT_LIMIT,
        **kwargs: Any,
    ) -> str:
        query = _clamp_text(symbol, "symbol", required=True)
        root = _resolve_repository_root(repository_path)
        access = _load_graph(root)
        depth_value = _bounded_int(depth, DEFAULT_DEPTH, 0, MAX_DEPTH)
        limit_value = _bounded_int(limit, DEFAULT_LIMIT, 1, MAX_LIMIT)

        base: Dict[str, Any] = {
            "tool": self.name,
            "query": query,
            "depth": depth_value,
            "graph": _graph_payload(access),
            "navigation_only": True,
            "disclaimer": NAVIGATION_DISCLAIMER,
        }
        if access.graph is None:
            base.update(
                {
                    "symbol_found": False,
                    "ambiguous": False,
                    "relationships": [],
                    "count": 0,
                    "truncated": False,
                }
            )
            return _json_output(base)

        matches, match_type = _resolve_symbol(access.graph, query)
        if not matches:
            base.update(
                {
                    "symbol_found": False,
                    "match_type": match_type,
                    "ambiguous": False,
                    "relationships": [],
                    "count": 0,
                    "truncated": False,
                }
            )
            return _json_output(base)

        if len(matches) > 1:
            base.update(
                {
                    "symbol_found": True,
                    "match_type": match_type,
                    "ambiguous": True,
                    "candidates": _symbol_candidates(matches, limit_value),
                    "relationships": [],
                    "count": 0,
                    "truncated": len(matches) > limit_value,
                    "note": "Multiple symbols matched; refine the query or pass a symbol_id.",
                }
            )
            return _json_output(base)

        chosen = matches[0]
        symbols_by_id, files_by_id = _node_index(access.graph)
        if self.relationship == "callers":
            hits = callers(access.graph, chosen.id, depth=depth_value)
            other_key = "source_id"
            direction = "caller"
        else:
            hits = callees(access.graph, chosen.id, depth=depth_value)
            other_key = "target_id"
            direction = "callee"

        relationships = []
        ambiguous_edges = 0
        for hit in hits:
            if hit.edge.resolution.value == "ambiguous":
                ambiguous_edges += 1
            other_id = getattr(hit, other_key)
            other = symbols_by_id.get(other_id)
            relationships.append(
                _relationship_entry(
                    direction=direction,
                    node=_symbol_payload(other, other_id),
                    hit=hit,
                    depth=hit.depth,
                )
            )

        unresolved = (
            len(access.result.unresolved_calls) if access.result is not None else 0
        )
        base.update(
            {
                "symbol_found": True,
                "match_type": match_type,
                "ambiguous": False,
                "resolved_symbol": _symbol_payload(chosen, chosen.id or ""),
                "relationships": relationships[:limit_value],
                "count": min(len(relationships), limit_value),
                "total_relationships": len(relationships),
                "truncated": len(relationships) > limit_value,
                "diagnostics": {
                    "ambiguous_edges": ambiguous_edges,
                    "unresolved_calls_in_graph": unresolved,
                },
                "files": {
                    file_id: _file_payload(files_by_id.get(file_id), file_id)
                    for file_id in sorted(
                        {
                            entry["node"].get("file_id")
                            for entry in relationships
                            if entry["node"].get("file_id")
                        }
                    )
                },
            }
        )
        return _json_output(base)


class GraphCallersTool(_SymbolQueryTool):
    """Read-only: find direct callers of a symbol."""

    name = "graph_callers"
    description = (
        "Find static CALLS relationships that target a symbol. Navigation "
        "evidence only; unresolved call sites are reported, never guessed."
    )
    relationship = "callers"


class GraphCalleesTool(_SymbolQueryTool):
    """Read-only: find direct callees of a symbol."""

    name = "graph_callees"
    description = (
        "Find static CALLS relationships originating from a symbol. Navigation "
        "evidence only; unresolved call sites are reported, never guessed."
    )
    relationship = "callees"


# ---------------------------------------------------------------------------
# Symbol lookup
# ---------------------------------------------------------------------------


class GraphFindSymbolTool(BaseTool):
    """Read-only: look up function/class/method/module symbols in the graph."""

    name = "graph_find_symbol"
    description = (
        "Locate symbols in the Code Graph by name, qualified name or canonical "
        "ID. Returns kind, qualified name, file path and source span; duplicate "
        "or ambiguous matches are reported explicitly."
    )
    permission_type = PermissionType.READ
    risk_level = RiskLevel.SAFE

    def get_parameter_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Symbol name, qualified name, or symbol:v1:... ID.",
                },
                "limit": LIMIT_SCHEMA,
                "repository_path": REPOSITORY_SCHEMA,
            },
            "required": ["query", "repository_path"],
        }

    def run(
        self,
        query: str,
        repository_path: str,
        limit: int = DEFAULT_LIMIT,
        **kwargs: Any,
    ) -> str:
        needle = _clamp_text(query, "query", required=True)
        root = _resolve_repository_root(repository_path)
        access = _load_graph(root)
        limit_value = _bounded_int(limit, DEFAULT_LIMIT, 1, MAX_LIMIT)

        payload: Dict[str, Any] = {
            "tool": self.name,
            "query": needle,
            "graph": _graph_payload(access),
            "navigation_only": True,
            "disclaimer": NAVIGATION_DISCLAIMER,
            "matches": [],
            "count": 0,
            "truncated": False,
            "ambiguous": False,
        }
        if access.graph is None:
            payload["match_type"] = "none"
            return _json_output(payload)

        matches, match_type = _resolve_symbol(access.graph, needle)
        payload["match_type"] = match_type
        payload["count"] = min(len(matches), limit_value)
        payload["total_matches"] = len(matches)
        payload["truncated"] = len(matches) > limit_value
        payload["matches"] = _symbol_candidates(matches, limit_value)

        # More than one matching definition (duplicate bare name, shared
        # qualified name, or a partial search) is reported as ambiguous rather
        # than silently choosing the first symbol.
        payload["ambiguous"] = len(matches) > 1
        if payload["ambiguous"]:
            payload["note"] = (
                "Multiple symbols matched; pass a qualified name or canonical "
                "symbol ID to disambiguate."
            )
        return _json_output(payload)


# ---------------------------------------------------------------------------
# Import relationships
# ---------------------------------------------------------------------------


class _FileImportTool(BaseTool):
    """Shared implementation for import/dependent file traversal."""

    permission_type = PermissionType.READ
    risk_level = RiskLevel.SAFE
    relationship: str = "imports"

    def get_parameter_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Repository-relative path of the file to inspect.",
                },
                "depth": DEPTH_SCHEMA,
                "limit": LIMIT_SCHEMA,
                "repository_path": REPOSITORY_SCHEMA,
            },
            "required": ["path", "repository_path"],
        }

    def run(
        self,
        path: str,
        repository_path: str,
        depth: int = DEFAULT_DEPTH,
        limit: int = DEFAULT_LIMIT,
        **kwargs: Any,
    ) -> str:
        raw_path = _clamp_text(path, "path", required=True)
        root = _resolve_repository_root(repository_path)
        # Containment guard: rejects traversal, absolute escapes and symlink
        # escapes before the path ever reaches the graph.
        PathValidator.resolve_safe_path(raw_path, str(root))
        normalized = normalize_repository_path(raw_path)

        access = _load_graph(root)
        depth_value = _bounded_int(depth, DEFAULT_DEPTH, 0, MAX_DEPTH)
        limit_value = _bounded_int(limit, DEFAULT_LIMIT, 1, MAX_LIMIT)

        payload: Dict[str, Any] = {
            "tool": self.name,
            "path": normalized,
            "depth": depth_value,
            "graph": _graph_payload(access),
            "navigation_only": True,
            "disclaimer": NAVIGATION_DISCLAIMER,
            "relationships": [],
            "count": 0,
            "truncated": False,
            "ambiguous": False,
        }
        if access.graph is None:
            payload["file_found"] = False
            return _json_output(payload)

        files_by_id = {file.id: file for file in access.graph.files}
        symbols_by_id = {symbol.id: symbol for symbol in access.graph.symbols}
        file_node = next(
            (file for file in access.graph.files if file.relative_path == normalized),
            None,
        )
        if file_node is None:
            payload["file_found"] = False
            payload["note"] = (
                "File is not present in the Code Graph (only supported source "
                "files are analyzed)."
            )
            return _json_output(payload)

        if self.relationship == "imports":
            hits = imports(access.graph, file_node.id, depth=depth_value)
            other_key = "target_id"
            direction = "imported_file"
        else:
            hits = dependents(access.graph, file_node.id, depth=depth_value)
            other_key = "source_id"
            direction = "dependent_file"

        relationships = []
        ambiguous_edges = 0
        for hit in hits:
            if hit.edge.resolution.value == "ambiguous":
                ambiguous_edges += 1
            other_id = getattr(hit, other_key)
            relationships.append(
                _relationship_entry(
                    direction=direction,
                    node=_file_payload(files_by_id.get(other_id), other_id),
                    hit=hit,
                    depth=hit.depth,
                )
            )

        unresolved_entries: List[Dict[str, Any]] = []
        if access.result is not None:
            for diagnostic in access.result.unresolved_imports:
                if diagnostic.relative_path == normalized:
                    unresolved_entries.append(
                        {
                            "code": diagnostic.code,
                            "message": diagnostic.message,
                            "line": diagnostic.line,
                        }
                    )

        payload.update(
            {
                "file_found": True,
                "file": _file_payload(file_node, file_node.id or ""),
                "relationships": relationships[:limit_value],
                "count": min(len(relationships), limit_value),
                "total_relationships": len(relationships),
                "truncated": len(relationships) > limit_value,
                "diagnostics": {
                    "ambiguous_edges": ambiguous_edges,
                    "unresolved_imports": unresolved_entries[:MAX_LIMIT],
                    "unresolved_import_count": len(unresolved_entries),
                },
                "symbols": {
                    symbol.id: _symbol_payload(symbol, symbol.id or "")
                    for symbol in sorted(
                        (
                            symbol
                            for symbol in symbols_by_id.values()
                            if symbol.file_id == file_node.id
                        ),
                        key=lambda symbol: symbol.id or "",
                    )[:limit_value]
                },
                "symbols_truncated": (
                    sum(1 for symbol in symbols_by_id.values() if symbol.file_id == file_node.id)
                    > limit_value
                ),
            }
        )
        return _json_output(payload)


class GraphImportsTool(_FileImportTool):
    """Read-only: list files imported by a file."""

    name = "graph_imports"
    description = (
        "List static IMPORTS relationships originating from a repository file. "
        "Resolved, unresolved and ambiguous imports are distinguished."
    )
    relationship = "imports"


class GraphDependentsTool(_FileImportTool):
    """Read-only: list files that import a file."""

    name = "graph_dependents"
    description = (
        "List static IMPORTS relationships targeting a repository file (its "
        "dependents). Navigation evidence only; not a runtime impact claim."
    )
    relationship = "dependents"


# ---------------------------------------------------------------------------
# Dependency / impact navigation
# ---------------------------------------------------------------------------


class GraphImpactTool(BaseTool):
    """Read-only: related symbols/files via existing graph queries."""

    name = "graph_impact"
    description = (
        "Navigate dependency/impact relationships for a symbol or file using "
        "existing Code Graph queries (callers, callees and file dependents). "
        "Static navigation only; does not claim runtime impact."
    )
    permission_type = PermissionType.READ
    risk_level = RiskLevel.SAFE

    def get_parameter_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "target": {
                    "type": "string",
                    "description": (
                        "Symbol name/qualified name/symbol ID, or a "
                        "repository-relative file path."
                    ),
                },
                "depth": DEPTH_SCHEMA,
                "limit": LIMIT_SCHEMA,
                "repository_path": REPOSITORY_SCHEMA,
            },
            "required": ["target", "repository_path"],
        }

    def run(
        self,
        target: str,
        repository_path: str,
        depth: int = 2,
        limit: int = DEFAULT_LIMIT,
        **kwargs: Any,
    ) -> str:
        needle = _clamp_text(target, "target", required=True)
        root = _resolve_repository_root(repository_path)
        access = _load_graph(root)
        depth_value = _bounded_int(depth, 2, 1, MAX_DEPTH)
        limit_value = _bounded_int(limit, DEFAULT_LIMIT, 1, MAX_LIMIT)

        payload: Dict[str, Any] = {
            "tool": self.name,
            "target": needle,
            "depth": depth_value,
            "graph": _graph_payload(access),
            "navigation_only": True,
            "runtime_impact_verified": False,
            "disclaimer": NAVIGATION_DISCLAIMER,
            "ambiguous": False,
            "related_symbols": [],
            "dependent_files": [],
            "count": 0,
            "truncated": False,
        }
        if access.graph is None:
            payload["target_found"] = False
            return _json_output(payload)

        symbols_by_id, files_by_id = _node_index(access.graph)
        matches, match_type = _resolve_symbol(access.graph, needle)
        target_kind = "symbol"
        file_node: Optional[FileNode] = None
        chosen: Optional[SymbolNode] = None

        if matches and len(matches) > 1:
            payload.update(
                {
                    "target_found": True,
                    "target_kind": target_kind,
                    "match_type": match_type,
                    "ambiguous": True,
                    "candidates": _symbol_candidates(matches, limit_value),
                    "note": "Multiple symbols matched; refine the target.",
                }
            )
            return _json_output(payload)

        if matches:
            chosen = matches[0]
            file_node = files_by_id.get(chosen.file_id)
        else:
            # Fall back to treating the target as a file path.
            try:
                PathValidator.resolve_safe_path(needle, str(root))
                normalized = normalize_repository_path(needle)
            except (SecurityViolationError, ValueError):
                normalized = None
            if normalized is not None:
                file_node = next(
                    (file for file in access.graph.files if file.relative_path == normalized),
                    None,
                )
            target_kind = "file"

        if chosen is None and file_node is None:
            payload.update({"target_found": False, "match_type": match_type})
            return _json_output(payload)

        related_symbols: List[Dict[str, Any]] = []
        dependent_files: List[Dict[str, Any]] = []

        if chosen is not None:
            for label, result in (
                ("caller", callers(access.graph, chosen.id, depth=depth_value)),
                ("callee", callees(access.graph, chosen.id, depth=depth_value)),
            ):
                other_key = "source_id" if label == "caller" else "target_id"
                for hit in result:
                    other_id = getattr(hit, other_key)
                    entry = _relationship_entry(
                        direction=label,
                        node=_symbol_payload(symbols_by_id.get(other_id), other_id),
                        hit=hit,
                        depth=hit.depth,
                    )
                    related_symbols.append(entry)

        if file_node is not None:
            for hit in dependents(access.graph, file_node.id, depth=depth_value):
                dependent_files.append(
                    _relationship_entry(
                        direction="dependent_file",
                        node=_file_payload(files_by_id.get(hit.source_id), hit.source_id),
                        hit=hit,
                        depth=hit.depth,
                    )
                )

        total_related = len(related_symbols) + len(dependent_files)
        related_symbols = related_symbols[:limit_value]
        dependent_files = dependent_files[: max(0, limit_value - len(related_symbols))]
        returned = len(related_symbols) + len(dependent_files)

        payload.update(
            {
                "target_found": True,
                "target_kind": target_kind,
                "match_type": match_type,
                "symbol": _symbol_payload(chosen, chosen.id) if chosen is not None else None,
                "file": _file_payload(file_node, file_node.id) if file_node is not None else None,
                "related_symbols": related_symbols,
                "dependent_files": dependent_files,
                "count": returned,
                "total_related": total_related,
                "truncated": total_related > returned,
            }
        )
        return _json_output(payload)


# ---------------------------------------------------------------------------
# Smart Context (Phase 11.9 retrieval integration)
# ---------------------------------------------------------------------------


class GraphContextTool(BaseTool):
    """Read-only: graph-guided retrieval through the existing hybrid retriever."""

    name = "graph_context"
    description = (
        "Retrieve repository context for a query using the existing hybrid "
        "retriever plus additive Code Graph candidates (Phase 11.9 adapter). "
        "Existing retrieval results, ranking and token budgets are preserved."
    )
    permission_type = PermissionType.READ
    risk_level = RiskLevel.SAFE

    def get_parameter_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Natural-language or symbol-oriented query.",
                },
                "depth": DEPTH_SCHEMA,
                "limit": {
                    "type": "integer",
                    "description": f"Maximum candidates to return (default 8, max {MAX_LIMIT}).",
                },
                "max_files": {
                    "type": "integer",
                    "description": (
                        f"Maximum repository files to chunk (default {MAX_CONTEXT_FILES})."
                    ),
                },
                "repository_path": REPOSITORY_SCHEMA,
            },
            "required": ["query", "repository_path"],
        }

    def run(
        self,
        query: str,
        repository_path: str,
        depth: int = DEFAULT_DEPTH,
        limit: int = 8,
        max_files: int = MAX_CONTEXT_FILES,
        **kwargs: Any,
    ) -> str:
        needle = _clamp_text(query, "query", required=True)
        root = _resolve_repository_root(repository_path)
        access = _load_graph(root)
        depth_value = _bounded_int(depth, DEFAULT_DEPTH, 0, MAX_DEPTH)
        limit_value = _bounded_int(limit, 8, 1, MAX_LIMIT)
        max_file_value = _bounded_int(max_files, MAX_CONTEXT_FILES, 1, MAX_CONTEXT_FILES)

        chunks, files_chunked, chunk_set_truncated = _repository_chunks(
            root, max_file_value
        )

        merged, retrieval_diagnostics = integrate_graph_into_retrieval(
            query=needle,
            graph=access.graph,  # None is the documented Phase 11.9 fallback
            chunks=chunks,
            vector_retriever=None,
            depth=depth_value,
        )

        candidates = [
            {
                "chunk_id": candidate.chunk_id,
                "file_path": candidate.file_path,
                "symbol_name": candidate.symbol_name,
                "symbol_type": candidate.symbol_type,
                "start_line": candidate.start_line,
                "end_line": candidate.end_line,
                "content_hash": candidate.content_hash,
                "final_score": candidate.final_score,
                "keyword_score": candidate.keyword_score,
                "symbol_score": candidate.symbol_score,
                "semantic_score": candidate.semantic_score,
            }
            for candidate in merged[:limit_value]
        ]

        payload = {
            "tool": self.name,
            "query": needle,
            "depth": depth_value,
            "graph": _graph_payload(access),
            "fallback_used": access.graph is None,
            "navigation_only": True,
            "disclaimer": NAVIGATION_DISCLAIMER,
            "candidates": candidates,
            "count": len(candidates),
            "total_candidates": len(merged),
            "truncated": len(merged) > limit_value,
            "retrieval_diagnostics": retrieval_diagnostics,
            "chunks": {
                "files_chunked": files_chunked,
                "chunk_count": len(chunks),
                "truncated": chunk_set_truncated,
                "max_files": max_file_value,
            },
        }
        return _json_output(payload)


def _repository_chunks(
    root: Path, max_files: int
) -> Tuple[List[Any], int, bool]:
    """Chunk a bounded subset of repository files using the existing chunker."""
    chunk_lists = chunk_repo(str(root), max_files=max_files)
    chunks: List[Any] = []
    files_chunked = 0
    truncated = False
    for chunk_list in chunk_lists:
        if files_chunked >= max_files:
            truncated = True
            break
        files_chunked += 1
        for chunk in chunk_list.chunks:
            if len(chunks) >= MAX_CONTEXT_CHUNKS:
                truncated = True
                break
            chunks.append(chunk)
        if len(chunks) >= MAX_CONTEXT_CHUNKS:
            truncated = True
            break
    return chunks, files_chunked, truncated


# ---------------------------------------------------------------------------
# Evidence Engine (Phase 7 + Phase 11.10)
# ---------------------------------------------------------------------------


class VerifyClaimTool(BaseTool):
    """Read-only: verify one code claim with existing Phase 7 verification."""

    name = "verify_claim"
    description = (
        "Verify a falsifiable code claim against repository source evidence "
        "using the existing verification engine plus graph navigation "
        "(Phase 11.10). Returns SUPPORTED, UNSUPPORTED or INCONCLUSIVE only."
    )
    permission_type = PermissionType.READ
    risk_level = RiskLevel.SAFE

    def get_parameter_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "claim": {
                    "type": "string",
                    "description": "The falsifiable statement to verify.",
                },
                "claim_type": {
                    "type": "string",
                    "description": (
                        "ClaimType value (default GENERIC). One of: "
                        + ", ".join(claim.value for claim in ClaimType)
                    ),
                },
                "claim_id": {
                    "type": "string",
                    "description": "Optional stable claim identifier.",
                },
                "target_file": {
                    "type": "string",
                    "description": "Repository-relative file the claim refers to.",
                },
                "target_line": {
                    "type": "integer",
                    "description": "1-based line the claim refers to.",
                },
                "expected_pattern": {
                    "type": "string",
                    "description": "Exact source text the claim asserts is present.",
                },
                "depth": DEPTH_SCHEMA,
                "repository_path": REPOSITORY_SCHEMA,
            },
            "required": ["claim", "repository_path"],
        }

    def run(
        self,
        claim: str,
        repository_path: str,
        claim_type: str = "GENERIC",
        claim_id: Optional[str] = None,
        target_file: Optional[str] = None,
        target_line: Optional[int] = None,
        expected_pattern: Optional[str] = None,
        depth: int = DEFAULT_DEPTH,
        **kwargs: Any,
    ) -> str:
        statement = _clamp_text(claim, "claim", required=True)
        root = _resolve_repository_root(repository_path)

        # The claim's target file is read by the existing evidence collector,
        # which trusts its input.  Contain it against the selected workspace
        # here so a claim cannot address files outside the repository.
        target_file_value = _clamp_text(target_file, "target_file")
        if target_file_value is not None:
            target_file_value = _contained_relative_path(target_file_value, root)

        try:
            parsed_type = ClaimType(str(claim_type).strip().upper())
        except ValueError as error:
            allowed = ", ".join(item.value for item in ClaimType)
            raise ValueError(
                f"Unsupported claim_type '{claim_type}'. Allowed values: {allowed}."
            ) from error

        line_value: Optional[int] = None
        if target_line is not None:
            try:
                line_value = int(target_line)
            except (TypeError, ValueError) as error:
                raise ValueError("target_line must be an integer.") from error
            if line_value < 1:
                raise ValueError("target_line is 1-based and must be >= 1.")

        fallback_claim_id = "clm_tool_" + hashlib.sha256(
            statement.encode("utf-8")
        ).hexdigest()[:12]
        extracted = ExtractedClaim(
            claim_id=(claim_id or "").strip() or fallback_claim_id,
            claim_type=parsed_type,
            statement=statement,
            target_file=target_file_value,
            target_line=line_value,
            expected_pattern=_clamp_text(expected_pattern, "expected_pattern"),
        )

        access = _load_graph(root)
        depth_value = _bounded_int(depth, DEFAULT_DEPTH, 0, MAX_DEPTH)
        outcome = verify_claim_with_graph(
            extracted,
            root,
            graph=access.graph,
            depth=depth_value,
        )

        # Guard the external contract: only the three documented statuses are
        # emitted, regardless of the internal verdict.
        status = outcome.status.value
        if status not in {"SUPPORTED", "UNSUPPORTED", "INCONCLUSIVE"}:
            status = "INCONCLUSIVE"

        evidence_summary = [
            {
                "evidence_id": span.evidence_id,
                "relative_path": span.relative_path,
                "line_start": span.line_start,
                "line_end": span.line_end,
                "relationship": span.relationship,
                "stale": span.stale,
                "stale_reason": span.stale_reason,
                "ambiguous": span.ambiguous,
                "navigation_only": span.navigation_only,
                "exact_match": span.exact_match,
                "declaration_match": span.declaration_match,
                "missing": span.missing,
                "corroborating": (
                    not span.missing
                    and not span.stale
                    and not span.ambiguous
                    and span.claim_relevant
                    and (span.exact_match or span.declaration_match)
                ),
            }
            for span in outcome.bundle.spans
        ]
        source_locations = [
            {
                "relative_path": span.relative_path,
                "line_start": span.line_start,
                "line_end": span.line_end,
                "relationship": span.relationship,
            }
            for span in outcome.bundle.spans
        ]

        payload = {
            "tool": self.name,
            "claim": {
                "claim_id": extracted.claim_id,
                "claim_type": extracted.claim_type.value,
                "statement": extracted.statement,
                "target_file": extracted.target_file,
                "target_line": extracted.target_line,
                "expected_pattern": extracted.expected_pattern,
            },
            "status": status,
            "verdict": {
                "status": outcome.verdict.status.value,
                "confidence": outcome.verdict.confidence,
                "explanation": outcome.verdict.explanation,
                "evidence_ids": list(outcome.verdict.evidence_ids),
            },
            "evidence_summary": evidence_summary,
            "source_locations": source_locations,
            "reasons": list(outcome.reasons),
            "diagnostics": outcome.bundle.diagnostics,
            "graph": _graph_payload(access),
            "navigation_only": True,
            "runtime_behavior_verified": False,
            "disclaimer": (
                "Graph relationships are navigation evidence. SUPPORTED requires "
                "fresh, unambiguous source evidence accepted by the existing "
                "verification engine; stale, ambiguous or navigation-only data "
                "can never support a claim."
            ),
        }
        return _json_output(payload)


__all__ = [
    "GraphFindSymbolTool",
    "GraphCallersTool",
    "GraphCalleesTool",
    "GraphImportsTool",
    "GraphDependentsTool",
    "GraphImpactTool",
    "GraphContextTool",
    "VerifyClaimTool",
]
