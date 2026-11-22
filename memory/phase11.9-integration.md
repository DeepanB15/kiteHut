# Phase 11.9 — Smart Context Integration: Architecture

## Files Changed

### New File: `backend/app/code_graph/integration.py`
Phase 11.9 module providing graph-guided context retrieval. Exports:

- `discover_graph_candidates(query, graph, depth=1)` — identifies relevant symbols/files via Code Graph traversal
- `get_callers_callees_imports(graph, symbol_id, depth=1)` — extracts relationship hits from the graph
- `merge_graph_candidates(existing_candidates, graph_candidates, config)` — merges graph influence with existing retrieval results
- `integrate_graph_into_retrieval(query, graph, chunks, vector_index, depth, retriever_config)` — full end-to-end adapter
- `build_graph_from_root(root_path)` — convenience for testing

### Key Design Decisions

1. **Graph is advisory only** — scores are adjusted, not asserted. Graph relationships do not replace existing retrieval logic.

2. **Graceful fallback** — if graph is None or has invalid schema_version, returns empty candidate list; existing retrieval continues unchanged.

3. **Deterministic ordering** — all graph candidate sorting follows the same patterns as existing retrieval (score DESC, chunk_id ASC for ties).

4. **Deduplication by chunk_id** — graph candidates are merged by chunk_id; overlapping candidates get graph-derived score bonuses; new candidates are appended.

5. **Per-branch score adjustments** — graph influence targets specific score components:
   - Symbol name matches: bonus to `symbol_score`
   - File path relevance: bonus to `path_bonus` via existing ranking infrastructure
   - Caller/callee relationships: adjusted through symbol/provenance metadata

6. **Depth-bounded BFS traversal** — uses existing `queries.py` patterns with explicit depth limits; cycles terminate naturally; each node visited at most once per query.

7. **Provenance preservation** — all returned candidates carry file paths, symbol names, line spans and source provenance from graph edges.

8. **Measurable and testable** — graph contributions are observable in final scores via `final_score` and `symbol_score` fields; diagnostics report candidate counts and merge stats.

### Integration Flow

```
User query
    → _extract_symbol_names()                    ← identify symbol names from query
    → discover_graph_candidates()                ← graph traversal (BFS, depth-bound)
    → HybridRetriever.retrieve()                 ← existing keyword/symbol/semantic
    → merge_graph_candidates()                   ← merge + score adjustments
    → ContextRanker.rank()                       ← existing deterministic ranking
    → ContextBuilder.build()                     ← existing budget-aware assembly
    → PromptBuilder.build_prompt()               ← existing LLM prompting
    → Local LLM                                  ← unchanged
```

### Score Adjustment Rules (additive, not replacement)

| Graph Influence | Target | Adjustment |
|---|---|---|
| Exact symbol name match | `symbol_score` | `cfg.symbol_weight * 0.3` |
| Partial symbol name match | `symbol_score` | `cfg.symbol_weight * 0.15` |
| Adjacent symbol (caller/callee) | `symbol_score` | `graph_score * cfg.symbol_weight` |
| Import dependency | `symbol_score` / `path_bonus` | `graph_score * cfg.symbol_weight` / `cfg.path_weight` |

### What Was NOT Done

- Did not redesign the frontend
- Did not introduce a new vector database or graph database
- Did not modify unrelated agent, MCP or security functionality
- Did not touch databases or migrations
- Did not stage, commit, push, reset, clean or discard changes
- Did not treat graph relationships as proof of source-code behavior
- Did not replace existing embedding/retrieval architecture

### Test Results

All 340 existing tests pass (4 skipped as before). New integration functions tested with:
- Direct symbol queries ("helper", "main", "other")
- Function and class queries
- Caller/callee context retrieval
- Import dependency context
- Graph and keyword candidate merging
- Duplicate removal (by chunk_id)
- Ranking behavior preservation
- Context token budget (existing infrastructure unchanged)
- Missing/invalid graph fallback (returns empty list, no errors)
- Existing retrieval regression (all scores and ordering preserved)