"""Phase 11.8 — query helpers over a validated :class:`CodeGraph`.

Queries are model-backed: they never mutate the graph, never infer new
edges and never consult NetworkX.  Traversal is breadth-first with a
caller-supplied ``depth`` bound; each node is visited at most once per
query, cycles terminate, and results are returned in deterministic order
(by depth, then canonical ID).

Every returned relationship carries the source path/span provenance from the
originating edge.  Unknown IDs yield empty results rather than raising, so
callers can distinguish "no such node" from "no edges" by the length of the
returned list.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.code_graph.models import (
    CodeGraph,
    EdgeKind,
    GraphEdge,
    SymbolNode,
)


@dataclass(frozen=True)
class RelationshipHit:
    """A resolved edge between two graph nodes, with provenance."""

    edge: GraphEdge
    source_id: str
    target_id: str
    depth: int

    @property
    def kind(self) -> EdgeKind:
        return self.edge.kind

    def provenance(self) -> Dict[str, Any]:
        return {
            "source_file": self.edge.source_file,
            "start_line": self.edge.start_line,
            "end_line": self.edge.end_line,
            "start_column": self.edge.start_column,
            "end_column": self.edge.end_column,
            "source_hash": self.edge.source_hash,
            "provenance_kind": self.edge.provenance_kind.value,
            "confidence": self.edge.confidence.value,
            "resolution": self.edge.resolution.value,
        }


@dataclass
class QueryResult:
    """Outcome of a traversal query; deterministic ordering by construction."""

    start_id: str
    depth: int
    hits: List[RelationshipHit] = field(default_factory=list)

    def __len__(self) -> int:  # pragma: no cover - convenience
        return len(self.hits)

    def __iter__(self):
        return iter(self.hits)


def _index(graph: CodeGraph):
    file_ids = {file.id for file in graph.files}
    symbol_ids = {symbol.id for symbol in graph.symbols}
    known_ids = file_ids | symbol_ids | {graph.repository.repository_id}

    outgoing: Dict[str, List[GraphEdge]] = {}
    incoming: Dict[str, List[GraphEdge]] = {}
    for edge in graph.edges:
        outgoing.setdefault(edge.source_id, []).append(edge)
        incoming.setdefault(edge.target_id, []).append(edge)
    for edges in outgoing.values():
        edges.sort(key=lambda edge: edge.id or "")
    for edges in incoming.values():
        edges.sort(key=lambda edge: edge.id or "")

    symbols_by_id = {symbol.id: symbol for symbol in graph.symbols}
    return known_ids, outgoing, incoming, symbols_by_id


def _traverse(
    graph: CodeGraph,
    start_id: str,
    *,
    depth: int,
    kinds: Optional[set[EdgeKind]],
    direction: str,
) -> QueryResult:
    if depth < 0:
        raise ValueError("depth must be >= 0")

    known_ids, outgoing, incoming, _ = _index(graph)
    result = QueryResult(start_id=start_id, depth=depth)
    if start_id not in known_ids or depth == 0:
        return result

    adjacency = outgoing if direction == "out" else incoming
    visited = {start_id}
    frontier = [start_id]

    for level in range(1, depth + 1):
        next_frontier: List[str] = []
        level_hits: List[RelationshipHit] = []
        for node_id in sorted(frontier):
            for edge in adjacency.get(node_id, []):
                if kinds is not None and edge.kind not in kinds:
                    continue
                other = edge.target_id if direction == "out" else edge.source_id
                level_hits.append(
                    RelationshipHit(
                        edge=edge,
                        source_id=edge.source_id,
                        target_id=edge.target_id,
                        depth=level,
                    )
                )
                if other not in visited:
                    visited.add(other)
                    next_frontier.append(other)
        level_hits.sort(key=lambda hit: (hit.edge.id or "", hit.source_id, hit.target_id))
        result.hits.extend(level_hits)
        if not next_frontier:
            break
        frontier = next_frontier

    return result


def find_symbols(
    graph: CodeGraph,
    name_or_qualified_name: str,
) -> List[SymbolNode]:
    """Return symbols whose ``name`` or ``qualified_name`` matches exactly.

    A non-empty, non-matching substring of either field also matches as a
    partial search when no exact matches are found.  Results are sorted by
    canonical symbol ID for deterministic output.
    """
    needle = (name_or_qualified_name or "").strip()
    if not needle:
        return []

    exact = [
        symbol
        for symbol in graph.symbols
        if symbol.name == needle or symbol.qualified_name == needle
    ]
    if exact:
        return sorted(exact, key=lambda symbol: symbol.id or "")

    needle_lower = needle.lower()
    partial = [
        symbol
        for symbol in graph.symbols
        if needle_lower in symbol.name.lower()
        or needle_lower in symbol.qualified_name.lower()
    ]
    return sorted(partial, key=lambda symbol: symbol.id or "")


def callers(graph: CodeGraph, symbol_id: str, depth: int = 1) -> QueryResult:
    """Return CALLS edges whose target is ``symbol_id`` (incoming, ≤ depth)."""
    return _traverse(graph, symbol_id, depth=depth, kinds={EdgeKind.CALLS}, direction="in")


def callees(graph: CodeGraph, symbol_id: str, depth: int = 1) -> QueryResult:
    """Return CALLS edges whose source is ``symbol_id`` (outgoing, ≤ depth)."""
    return _traverse(graph, symbol_id, depth=depth, kinds={EdgeKind.CALLS}, direction="out")


def imports(graph: CodeGraph, file_id: str, depth: int = 1) -> QueryResult:
    """Return IMPORTS edges whose source is ``file_id`` (outgoing, ≤ depth)."""
    return _traverse(graph, file_id, depth=depth, kinds={EdgeKind.IMPORTS}, direction="out")


def dependents(graph: CodeGraph, file_id: str, depth: int = 1) -> QueryResult:
    """Return IMPORTS edges whose target is ``file_id`` (incoming, ≤ depth)."""
    return _traverse(graph, file_id, depth=depth, kinds={EdgeKind.IMPORTS}, direction="in")


__all__ = [
    "QueryResult",
    "RelationshipHit",
    "find_symbols",
    "callers",
    "callees",
    "imports",
    "dependents",
]
