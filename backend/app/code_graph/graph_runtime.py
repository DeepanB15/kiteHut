"""Phase 11.8 — NetworkX projection for the Code Graph.

NetworkX is a *projection/runtime* dependency only.  The canonical,
serialized representation of a graph remains the :class:`CodeGraph` model;
``to_networkx`` builds an in-memory :class:`networkx.MultiDiGraph` view for
traversal tooling.

The import is deliberately deferred so that ``app.code_graph`` can be used
without NetworkX installed.  Calling :func:`to_networkx` without NetworkX
available raises :class:`RuntimeError` with an explicit message instead of
falling back to a success-shaped partial graph.
"""

from __future__ import annotations

from typing import Any, Dict, List

from app.code_graph.models import CodeGraph, GraphEdge


def _load_networkx():
    try:
        import networkx as nx  # type: ignore
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise RuntimeError(
            "NetworkX is required for app.code_graph.graph_runtime. "
            "Install it with `python -m pip install networkx`."
        ) from exc
    return nx


def to_networkx(graph: CodeGraph):
    """Project a :class:`CodeGraph` onto a ``networkx.MultiDiGraph``.

    Node attributes carry ``node_kind`` (``repository``/``file``/``symbol``)
    plus the identifying fields for that kind.  Edge attributes preserve
    ``kind``, ``provenance_kind``, provenance path/span, ``source_hash``,
    ``confidence``, ``resolution``, ``extractor`` and ``metadata``.

    Parallel edges are preserved (``MultiDiGraph``); edge identity is the
    multi-edge key, so repeated builds yield identical projections.
    """
    nx = _load_networkx()

    projected = nx.MultiDiGraph()
    projected.graph["schema_version"] = graph.schema_version
    projected.graph["repository_id"] = graph.repository.repository_id
    if graph.source_digest is not None:
        projected.graph["source_digest"] = graph.source_digest

    repository = graph.repository
    projected.add_node(
        repository.repository_id,
        node_kind="repository",
        repository_id=repository.repository_id,
        name=repository.name,
        root_path=repository.root_path,
    )

    for file_node in graph.files:
        projected.add_node(
            file_node.id,
            node_kind="file",
            repository_id=file_node.repository_id,
            relative_path=file_node.relative_path,
            language=file_node.language,
            content_hash=file_node.content_hash,
            line_count=file_node.line_count,
            byte_size=file_node.byte_size,
        )

    for symbol in graph.symbols:
        projected.add_node(
            symbol.id,
            node_kind="symbol",
            repository_id=symbol.repository_id,
            file_id=symbol.file_id,
            relative_path=symbol.relative_path,
            name=symbol.name,
            qualified_name=symbol.qualified_name,
            kind=symbol.kind.value,
            parent_id=symbol.parent_id,
            start_line=symbol.start_line,
            end_line=symbol.end_line,
            start_column=symbol.start_column,
            end_column=symbol.end_column,
            source_hash=symbol.source_hash,
            extractor=symbol.extractor,
            occurrence_ordinal=symbol.occurrence_ordinal,
        )

    edge_data: Dict[str, Any] = {}
    for edge in graph.edges:
        key = _edge_key(edge)
        projected.add_edge(
            edge.source_id,
            edge.target_id,
            key=key,
            id=edge.id,
            kind=edge.kind.value,
            provenance_kind=edge.provenance_kind.value,
            source_file=edge.source_file,
            start_line=edge.start_line,
            end_line=edge.end_line,
            start_column=edge.start_column,
            end_column=edge.end_column,
            source_hash=edge.source_hash,
            confidence=edge.confidence.value,
            resolution=edge.resolution.value,
            extractor=edge.extractor,
            metadata=dict(edge.metadata),
            repository_id=edge.repository_id,
        )
        edge_data[key] = edge

    return projected


def _edge_key(edge: GraphEdge) -> str:
    """Stable multi-edge key; edges already carry deterministic IDs."""
    return edge.id or ""


def edge_provenance_summary(edge: GraphEdge) -> Dict[str, Any]:
    """Compact provenance dictionary suitable for query result payloads."""
    return {
        "id": edge.id,
        "kind": edge.kind.value,
        "provenance_kind": edge.provenance_kind.value,
        "source_file": edge.source_file,
        "start_line": edge.start_line,
        "end_line": edge.end_line,
        "start_column": edge.start_column,
        "end_column": edge.end_column,
        "source_hash": edge.source_hash,
        "confidence": edge.confidence.value,
        "resolution": edge.resolution.value,
        "extractor": edge.extractor,
    }


__all__ = ["to_networkx", "edge_provenance_summary"]
