"""Phase 11.9 — Smart Context Integration: Code Graph-guided retrieval.

This module adds graph-guided candidate discovery to the existing retrieval
pipeline without replacing any existing architecture.  It identifies relevant
files and symbols via the public Code Graph query layer and merges those
candidates with existing ``HybridRetriever`` results.

Key design principles:
- Graph data is advisory only; scores are adjusted, never asserted.
- Graph contributions are observable in the returned diagnostics and in the
  recomputed ``final_score`` of adjusted candidates.
- Missing or invalid graph artifacts are handled gracefully (fallback to the
  existing retrieval results).
- Deduplication uses the existing chunk/symbol identity (``chunk_id``).
- Ranking reuses the existing ``HybridRetriever`` scoring weights and
  deterministic tie-break; graph candidates are additive, never a replacement.
- Traversal is delegated to ``app.code_graph.queries`` — there is no second
  graph traversal engine in this module.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, Tuple

from app.code_graph.models import (
    CODE_GRAPH_SCHEMA_VERSION,
    CodeGraph,
    FileNode,
    SymbolNode,
)
from app.code_graph.queries import (
    callers,
    callees,
    find_symbols,
    imports,
)
from app.retrieval.hybrid.retrieval import (
    HybridRetrievalConfig,
    HybridRetrievalResult,
    HybridRetriever,
    RetrievalCandidate,
    tokenize_query,
)
from app.retrieval.retrieval import VectorRetrieval


# ---------------------------------------------------------------------------
# Query understanding: identify symbol names from user query
# ---------------------------------------------------------------------------

def _extract_symbol_names(query: str) -> List[str]:
    """Extract potential symbol names from a user query.

    Uses the existing deterministic tokenizer and keeps identifier-like tokens
    of at least two characters.
    """
    tokens = tokenize_query(query)
    return [token for token in tokens if len(token) >= 2]


# ---------------------------------------------------------------------------
# Graph candidate discovery
# ---------------------------------------------------------------------------

def _symbols_from_graph(
    graph: CodeGraph, symbol_names: List[str]
) -> List[SymbolNode]:
    """Look up symbols by name/qualified name, preserving deterministic order."""
    if graph is None or not symbol_names:
        return []

    seen: Set[str] = set()
    matched: List[SymbolNode] = []
    for needle in symbol_names:
        for symbol in find_symbols(graph, needle):
            if symbol.id is not None and symbol.id not in seen:
                seen.add(symbol.id)
                matched.append(symbol)
    return matched


def _node_indexes(
    graph: CodeGraph,
) -> Tuple[Dict[str, SymbolNode], Dict[str, FileNode]]:
    return (
        {symbol.id: symbol for symbol in graph.symbols if symbol.id is not None},
        {file_node.id: file_node for file_node in graph.files if file_node.id is not None},
    )


def _edge_provenance(hit: Any) -> Dict[str, Any]:
    """Compact provenance for a query hit (already includes resolution)."""
    provenance = hit.provenance()
    provenance["edge_id"] = hit.edge.id
    provenance["edge_kind"] = hit.edge.kind.value
    return provenance


def _node_candidate(
    node_id: str,
    *,
    symbols_by_id: Dict[str, SymbolNode],
    files_by_id: Dict[str, FileNode],
    graph_score: float,
    depth: int,
    provenance: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """Build one candidate dict from a graph node, or None if unresolvable."""
    symbol = symbols_by_id.get(node_id)
    if symbol is not None:
        return {
            "chunk_id": symbol.id,
            "file_path": symbol.relative_path,
            "symbol_name": symbol.name,
            "symbol_type": symbol.kind.value,
            "kind": "symbol",
            "start_line": symbol.start_line,
            "end_line": symbol.end_line,
            "content_hash": symbol.source_hash,
            "graph_score": graph_score,
            "provenance": provenance,
            "depth": depth,
        }

    file_node = files_by_id.get(node_id)
    if file_node is not None:
        return {
            "chunk_id": file_node.id,
            "file_path": file_node.relative_path,
            "symbol_name": None,
            "symbol_type": "file",
            "kind": "file",
            "start_line": 1,
            "end_line": max(1, file_node.line_count),
            "content_hash": file_node.content_hash,
            "graph_score": graph_score,
            "provenance": provenance,
            "depth": depth,
        }
    return None


def discover_graph_candidates(
    query: str,
    graph: Optional[CodeGraph],
    depth: int = 1,
) -> List[Dict[str, Any]]:
    """Discover graph candidates relevant to ``query``.

    The graph is used to locate query-named symbols and then, within the
    bounded ``depth``, their callers, callees and the imports of the file that
    declares them.  Every candidate carries its static provenance.

    Returns a deterministic list of candidate dicts with keys ``chunk_id``,
    ``file_path``, ``symbol_name``, ``symbol_type``, ``kind``, ``start_line``,
    ``end_line``, ``content_hash``, ``graph_score``, ``provenance`` and
    ``depth``.  A missing or unsupported graph yields ``[]`` (graceful
    fallback).
    """
    if graph is None:
        return []
    if getattr(graph, "schema_version", None) != CODE_GRAPH_SCHEMA_VERSION:
        return []

    symbol_names = _extract_symbol_names(query)
    if not symbol_names:
        return []

    matched_symbols = _symbols_from_graph(graph, symbol_names)
    if not matched_symbols:
        return []

    symbols_by_id, files_by_id = _node_indexes(graph)
    bounded_depth = max(0, depth)
    candidates: Dict[str, Dict[str, Any]] = {}

    def add(candidate: Optional[Dict[str, Any]]) -> None:
        if candidate is None:
            return
        chunk_id = candidate["chunk_id"]
        existing = candidates.get(chunk_id)
        # Keep the strongest graph score, then the shallowest depth.
        if existing is None or (
            candidate["graph_score"],
            -candidate["depth"],
        ) > (existing["graph_score"], -existing["depth"]):
            candidates[chunk_id] = candidate

    for symbol in matched_symbols:
        if symbol.id is None:
            continue

        base_score = 1.0 if symbol.name in symbol_names else 0.7
        add(
            _node_candidate(
                symbol.id,
                symbols_by_id=symbols_by_id,
                files_by_id=files_by_id,
                graph_score=base_score,
                depth=0,
                provenance={
                    "source_file": symbol.relative_path,
                    "start_line": symbol.start_line,
                    "end_line": symbol.end_line,
                    "provenance_kind": "declaration",
                    "confidence": "exact",
                    "resolution": "resolved",
                },
            )
        )

        for hit in callees(graph, symbol.id, depth=bounded_depth):
            add(
                _node_candidate(
                    hit.target_id,
                    symbols_by_id=symbols_by_id,
                    files_by_id=files_by_id,
                    graph_score=base_score * 0.8,
                    depth=hit.depth,
                    provenance=_edge_provenance(hit),
                )
            )

        for hit in callers(graph, symbol.id, depth=bounded_depth):
            add(
                _node_candidate(
                    hit.source_id,
                    symbols_by_id=symbols_by_id,
                    files_by_id=files_by_id,
                    graph_score=base_score * 0.7,
                    depth=hit.depth,
                    provenance=_edge_provenance(hit),
                )
            )

        # IMPORTS edges connect files, so anchor import navigation on the
        # declaring file rather than the symbol.
        if symbol.file_id is not None:
            for hit in imports(graph, symbol.file_id, depth=bounded_depth):
                add(
                    _node_candidate(
                        hit.target_id,
                        symbols_by_id=symbols_by_id,
                        files_by_id=files_by_id,
                        graph_score=base_score * 0.6,
                        depth=hit.depth,
                        provenance=_edge_provenance(hit),
                    )
                )

    return [
        candidate
        for candidate in sorted(
            candidates.values(),
            key=lambda candidate: (-candidate["graph_score"], candidate["chunk_id"]),
        )
    ]


def get_callers_callees_imports(
    graph: Optional[CodeGraph],
    symbol_id: str,
    depth: int = 1,
) -> Dict[str, List[Dict[str, Any]]]:
    """Extract callers, callees and file imports for a symbol.

    Thin projection over the public query helpers; unknown IDs yield empty
    lists rather than raising.
    """
    result: Dict[str, List[Dict[str, Any]]] = {
        "callers": [],
        "callees": [],
        "imports": [],
    }
    if graph is None:
        return result

    symbols_by_id, files_by_id = _node_indexes(graph)
    symbol = symbols_by_id.get(symbol_id)
    if symbol is None:
        return result

    for hit in callers(graph, symbol_id, depth=depth):
        candidate = _node_candidate(
            hit.source_id,
            symbols_by_id=symbols_by_id,
            files_by_id=files_by_id,
            graph_score=0.7,
            depth=hit.depth,
            provenance=_edge_provenance(hit),
        )
        if candidate is not None:
            result["callers"].append(candidate)

    for hit in callees(graph, symbol_id, depth=depth):
        candidate = _node_candidate(
            hit.target_id,
            symbols_by_id=symbols_by_id,
            files_by_id=files_by_id,
            graph_score=0.8,
            depth=hit.depth,
            provenance=_edge_provenance(hit),
        )
        if candidate is not None:
            result["callees"].append(candidate)

    if symbol.file_id is not None:
        for hit in imports(graph, symbol.file_id, depth=depth):
            candidate = _node_candidate(
                hit.target_id,
                symbols_by_id=symbols_by_id,
                files_by_id=files_by_id,
                graph_score=0.6,
                depth=hit.depth,
                provenance=_edge_provenance(hit),
            )
            if candidate is not None:
                result["imports"].append(candidate)

    return result


def _align_candidates_to_chunks(
    graph_candidates: List[Dict[str, Any]], chunks: List[Any]
) -> List[Dict[str, Any]]:
    """Map graph candidates onto the existing chunk identity where possible.

    Graph nodes use canonical ``symbol:v1:``/``file:v1:`` IDs while retrieval
    candidates use chunk hashes.  Without alignment the same source location
    would appear twice and graph candidates could never deduplicate against
    retrieval results.  Alignment uses the chunk's own identity contract:
    exact file path + source span first, then an unambiguous path + symbol
    match.  Ambiguous matches are left unaligned rather than attached to an
    arbitrary chunk, so those graph candidates remain additive.
    """
    by_symbol: Dict[Tuple[str, str], List[str]] = {}
    by_span: Dict[Tuple[str, int, int], List[str]] = {}
    chunks_by_id: Dict[str, Any] = {}
    for chunk in chunks:
        file_path = getattr(chunk, "file_path", None)
        chunk_id = getattr(chunk, "chunk_id", None)
        if not file_path or not chunk_id:
            continue
        chunks_by_id[chunk_id] = chunk
        symbol_name = getattr(chunk, "symbol_name", None)
        if symbol_name:
            bucket = by_symbol.setdefault((file_path, symbol_name), [])
            if chunk_id not in bucket:
                bucket.append(chunk_id)
        start_line = getattr(chunk, "start_line", None)
        end_line = getattr(chunk, "end_line", None)
        if start_line is not None and end_line is not None:
            bucket = by_span.setdefault((file_path, start_line, end_line), [])
            if chunk_id not in bucket:
                bucket.append(chunk_id)

    def _unique(ids: List[str]) -> Optional[str]:
        return ids[0] if len(ids) == 1 else None

    aligned: List[Dict[str, Any]] = []
    for candidate in graph_candidates:
        file_path = candidate.get("file_path")
        symbol_name = candidate.get("symbol_name")
        start_line = candidate.get("start_line")
        end_line = candidate.get("end_line")
        chunk_id: Optional[str] = None

        # 1. Exact source-span identity is the strongest signal.  If more than
        #    one chunk shares the span, only a matching symbol name can
        #    disambiguate it; otherwise the mapping is left unresolved.
        if file_path and start_line is not None and end_line is not None:
            span_matches = by_span.get((file_path, start_line, end_line), [])
            chunk_id = _unique(span_matches)
            if chunk_id is None and symbol_name:
                chunk_id = _unique(
                    [
                        cid
                        for cid in span_matches
                        if getattr(chunks_by_id.get(cid), "symbol_name", None)
                        == symbol_name
                    ]
                )

        # 2. Fall back to symbol identity only when it is unambiguous.  Never
        #    silently attach a graph node to the first of several same-name
        #    chunks: keep it independent instead.
        if chunk_id is None and file_path and symbol_name:
            chunk_id = _unique(by_symbol.get((file_path, symbol_name), []))

        if chunk_id is not None and chunk_id != candidate.get("chunk_id"):
            candidate = dict(candidate)
            candidate["graph_chunk_id"] = candidate["chunk_id"]
            candidate["chunk_id"] = chunk_id
        aligned.append(candidate)
    return aligned


# ---------------------------------------------------------------------------
# Candidate merging: graph + existing retrieval
# ---------------------------------------------------------------------------

def _final_score(
    keyword_score: float,
    symbol_score: float,
    semantic_score: float,
    config: HybridRetrievalConfig,
) -> float:
    """Reuse the existing candidate scoring contract (no new ranker)."""
    return RetrievalCandidate(
        chunk_id="",
        keyword_score=keyword_score,
        symbol_score=symbol_score,
        semantic_score=semantic_score,
    ).final_score(config)


def _copy_result(
    result: HybridRetrievalResult,
    *,
    symbol_score: float,
    config: HybridRetrievalConfig,
) -> HybridRetrievalResult:
    """Copy a retrieval result, adjusting only the symbol branch score."""
    return HybridRetrievalResult(
        chunk_id=result.chunk_id,
        final_score=_final_score(
            result.keyword_score, symbol_score, result.semantic_score, config
        ),
        keyword_score=result.keyword_score,
        symbol_score=symbol_score,
        semantic_score=result.semantic_score,
        file_path=result.file_path,
        symbol_name=result.symbol_name,
        symbol_type=result.symbol_type,
        start_line=result.start_line,
        end_line=result.end_line,
        content_hash=result.content_hash,
    )


def merge_graph_candidates(
    existing_candidates: List[HybridRetrievalResult],
    graph_candidates: List[Dict[str, Any]],
    config: Optional[HybridRetrievalConfig] = None,
) -> List[HybridRetrievalResult]:
    """Merge graph-guided candidates with existing retrieval results.

    Existing results are preserved (copied, never mutated) and keep their
    keyword/semantic branch scores.  When a graph candidate shares a
    ``chunk_id`` with an existing result, only its symbol branch score is
    raised to the graph-derived score and ``final_score`` is recomputed with
    the existing hybrid weights.  New graph candidates are appended.

    The combined list is ordered with the existing retriever's deterministic
    tie-break, so existing ranking behaviour is preserved rather than
    replaced.
    """
    cfg = config or HybridRetrievalConfig()

    merged_by_id: Dict[str, HybridRetrievalResult] = {}
    for result in existing_candidates:
        if result.chunk_id in merged_by_id:
            continue
        merged_by_id[result.chunk_id] = HybridRetrievalResult(
            chunk_id=result.chunk_id,
            final_score=result.final_score,
            keyword_score=result.keyword_score,
            symbol_score=result.symbol_score,
            semantic_score=result.semantic_score,
            file_path=result.file_path,
            symbol_name=result.symbol_name,
            symbol_type=result.symbol_type,
            start_line=result.start_line,
            end_line=result.end_line,
            content_hash=result.content_hash,
        )

    for candidate in graph_candidates:
        chunk_id = candidate.get("chunk_id")
        if not chunk_id:
            continue
        graph_score = float(candidate.get("graph_score", 0.0))

        existing = merged_by_id.get(chunk_id)
        if existing is not None:
            if graph_score <= existing.symbol_score:
                continue
            merged_by_id[chunk_id] = _copy_result(
                existing, symbol_score=graph_score, config=cfg
            )
            continue

        merged_by_id[chunk_id] = HybridRetrievalResult(
            chunk_id=chunk_id,
            final_score=_final_score(0.0, graph_score, 0.0, cfg),
            keyword_score=0.0,
            symbol_score=graph_score,
            semantic_score=0.0,
            file_path=candidate.get("file_path"),
            symbol_name=candidate.get("symbol_name"),
            symbol_type=candidate.get("symbol_type"),
            start_line=candidate.get("start_line"),
            end_line=candidate.get("end_line"),
            content_hash=candidate.get("content_hash"),
        )

    merged = list(merged_by_id.values())
    merged.sort(
        key=lambda result: (
            -result.final_score,
            -result.semantic_score,
            -result.symbol_score,
            -result.keyword_score,
            result.chunk_id,
        )
    )
    return merged


# ---------------------------------------------------------------------------
# Pipeline adapter: integrate graph into retrieval flow
# ---------------------------------------------------------------------------

def integrate_graph_into_retrieval(
    query: str,
    graph: Optional[CodeGraph],
    chunks: List[Any],
    vector_retriever: Optional[VectorRetrieval] = None,
    depth: int = 1,
    retriever_config: Optional[HybridRetrievalConfig] = None,
) -> Tuple[List[HybridRetrievalResult], Dict[str, Any]]:
    """Run existing hybrid retrieval, then add graph-guided candidates.

    The existing ``HybridRetriever`` is constructed exactly as callers already
    do (same chunks, config, vector retriever and branch limits) and its
    ``top_k`` budget is unchanged.  Graph candidates are additive: they can
    raise a shared candidate's symbol branch score or append new candidates,
    but they never remove or re-weight an existing branch.

    Returns ``(merged_results, graph_diagnostics)``.
    """
    cfg = retriever_config or HybridRetrievalConfig()

    graph_valid = (
        graph is not None
        and getattr(graph, "schema_version", None) == CODE_GRAPH_SCHEMA_VERSION
    )

    hybrid_retriever = HybridRetriever(
        chunks=chunks,
        vector_retriever=vector_retriever,
        config=cfg,
    )
    retrieval_results = hybrid_retriever.retrieve(query=query, top_k=20)

    graph_candidates = _align_candidates_to_chunks(
        discover_graph_candidates(query, graph, depth=depth), chunks
    )

    existing_ids = {result.chunk_id for result in retrieval_results}
    graph_ids = {candidate["chunk_id"] for candidate in graph_candidates}

    merged = merge_graph_candidates(retrieval_results, graph_candidates, config=cfg)
    merged_by_id = {result.chunk_id: result for result in merged}
    original_by_id = {result.chunk_id: result for result in retrieval_results}

    provenance_by_chunk: Dict[str, Any] = {}
    for candidate in graph_candidates:
        provenance_by_chunk.setdefault(
            candidate["chunk_id"], candidate.get("provenance", {})
        )
        if len(provenance_by_chunk) >= 20:
            break

    adjusted = 0
    for chunk_id in existing_ids & graph_ids:
        before = original_by_id[chunk_id]
        after = merged_by_id.get(chunk_id)
        if after is not None and after.symbol_score > before.symbol_score:
            adjusted += 1

    diagnostics: Dict[str, Any] = {
        "graph_available": graph is not None,
        "graph_valid": graph_valid,
        "graph_candidates_found": len(graph_candidates),
        "graph_candidates_merged": len(existing_ids & graph_ids),
        "graph_candidates_new": len(graph_ids - existing_ids),
        "graph_score_adjustments": adjusted,
        "retrieval_candidates_before_merge": len(retrieval_results),
        "retrieval_candidates_after_merge": len(merged),
        "graph_candidate_provenance": provenance_by_chunk,
        "fallback_used": not graph_valid,
    }
    return merged, diagnostics


# ---------------------------------------------------------------------------
# Convenience: build a minimal graph from a repo root for testing
# ---------------------------------------------------------------------------

def build_graph_from_root(root_path: str) -> Optional[CodeGraph]:
    """Build a CodeGraph from a repository root path.

    Convenience for testing; returns None if the build fails.
    """
    try:
        from app.code_graph.builder import CodeGraphBuilder
        from app.code_graph.discovery import RepositoryScanner

        scanner = RepositoryScanner(root_path)
        builder = CodeGraphBuilder(root_path, scanner=scanner)
        result = builder.build()
        if result.graph is not None:
            return result.graph
    except Exception:
        pass
    return None


__all__ = [
    "discover_graph_candidates",
    "get_callers_callees_imports",
    "merge_graph_candidates",
    "integrate_graph_into_retrieval",
    "build_graph_from_root",
]
