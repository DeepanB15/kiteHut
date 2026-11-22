# Phase 11.9 — Smart Context Integration: Audit Report

## Commit `a210325` — Completed Work (Phases 11.5-11.8)

### 11.5: Graph Validation (`backend/app/code_graph/validation.py`)
- 8 deterministic validation checks on assembled CodeGraph
- Node/edge ID uniqueness, endpoint validity, repository ownership
- File/symbol reference determinism, source spans, structural consistency
- Provenance consistency, contradiction detection
- `validate_graph()` entry point returns `GraphValidationResult`

### 11.6: Builder Pipeline (`backend/app/code_graph/builder.py`)
- Full pipeline: discover → extract → resolve → assemble → validate → GraphBuildResult
- Status outcomes: COMPLETE, PARTIAL, FAILED
- Deterministic ordering, atomic serialization support

### 11.7: Serialization (`backend/app/code_graph/serialization.py`)
- `serialize_graph_json()` — canonical JSON with sorted keys, compact separators
- `deserialize_graph_json()` — parse, schema version gate, validate
- `write_graph_file()` — atomic write with existing file protection
- `build_and_serialize()` — end-to-end convenience

### 11.8: Query Helpers (`backend/app/code_graph/queries.py`)
- `find_symbols()` — exact/partial symbol name lookup
- `callers()` — bounded BFS incoming CALLS traversal
- `callees()` — bounded BFS outgoing CALLS traversal
- `imports()` — bounded IMPORTS outgoing traversal
- `dependents()` — bounded IMPORTS incoming traversal
- Deterministic ordering, cycle termination, provenance payloads

## Existing Retrieval Architecture (Phases 8.1-8.6)

### 8.1: Chunking (`backend/app/chunking/model.py`)
- `CodeChunk` — deterministic semantic chunk with chunk_id, file_path, symbol_name, symbol_type, line spans, content, content_hash

### 8.2: Embedding (`backend/app/embedding/record.py`)
- `EmbeddingRecord` — chunk_id, content_hash, model_name, dimension, vector

### 8.3: Vector Retrieval (`backend/app/retrieval/local_index.py`)
- `LocalVectorIndex` — brute-force cosine similarity
- `VectorRetrieval` — high-level API over LocalVectorIndex

### 8.4: Hybrid Retrieval (`backend/app/retrieval/hybrid/retrieval.py`)
- `HybridRetriever` — combines keyword, symbol, and semantic retrieval
- Candidate merging by chunk_id, weighted fusion with configurable weights
- Deterministic ranking: score DESC, semantic DESC, symbol DESC, keyword DESC, chunk_id ASC

### 8.5: Context Ranking (`backend/app/context/ranking.py`)
- `ContextRanker` — deterministic ranking of HybridRetrievalResult candidates
- Signals: base relevance, exact match bonus, symbol bonus, path bonus, diversity bonus, redundancy penalty
- Deduplication by chunk_id, overlap penalty for same-file/line-range candidates
- Diversity bonus for new files, max_chunks/max_characters budget enforcement
- RankingBreakdown for transparency

### 8.6: RAG Pipeline (`backend/app/rag/pipeline.py`)
- End-to-end flow: query → hybrid retrieval → context ranking → context building → prompt building → LLM generation
- `RagPipeline.answer_query()` coordinates all components

## Step 3: Graph-Guided Context Integration Design

### Intended Flow
```
User query
→ Query understanding / symbol identification
→ Code Graph candidate discovery              ← NEW
→ Existing keyword, symbol and semantic retrieval
→ Candidate merging and deduplication
→ Context ranking
→ Token-budget-aware context assembly
→ Existing LLM pipeline
```

### Key Requirements (from spec)
1. **Use Code Graph to identify relevant files and symbols** — via `find_symbols`, `callers`, `callees`, `imports`, `dependents`
2. **Retrieve related callers, callees, imports and dependencies within bounded limits** — depth-bounded BFS
3. **Combine graph candidates with existing retrieval results** — merge into hybrid candidate list
4. **Preserve existing ranking behavior and retrieval compatibility** — no breaking changes to existing APIs
5. **Avoid duplicate chunks and irrelevant context** — deduplication by chunk_id
6. **Preserve file paths, symbol names, line spans and source provenance** — all returned candidates carry this metadata
7. **Handle unavailable or invalid graph artifacts gracefully** — fallback to existing retrieval when graph is missing/invalid
8. **Do not treat graph relationships as proof of source-code behavior** — graph data is advisory only, scores are adjusted not asserted
9. **Keep the existing embedding and retrieval architecture; do not replace it** — graph is an additional signal layer
10. **Make graph-guided retrieval measurable and testable** — all graph contributions are observable in scores and diagnostics

### Integration Points

The graph-guided retrieval will integrate at these points:

1. **New module**: `backend/app/code_graph/integration.py`
   - `discover_graph_candidates(query, graph, depth=1)` — identifies relevant symbols/files via graph traversal
   - `get_callers_callees_imports(graph, symbol_id, depth=1)` — extracts relationship hits

2. **Modified flow in RAG pipeline** or new adapter:
   - After hybrid retrieval, run graph candidate discovery
   - Merge graph candidates with existing HybridRetrievalResult candidates
   - Adjust scores based on graph proximity (bonus/penalty)
   - Pass merged candidates to existing ContextRanker

3. **Score adjustment logic**:
   - Graph symbol match: +0.05 to symbol_score (exact) or +0.025 (partial)
   - Graph file relevance: +0.02 to path_bonus if file appears in graph
   - Caller/callee relationship: +0.03 if query involves related symbols
   - These are additive bonuses, not replacements for existing scores

### What Will NOT Be Done
- Do not redesign the frontend
- Do not introduce a new vector database or graph database
- Do not modify unrelated agent, MCP or security functionality
- Do not touch databases or migrations
- Do not stage, commit, push, reset, clean or discard changes
- Do not treat graph relationships as proof of source-code behavior
- Do not replace existing embedding/retrieval architecture

## Test Coverage Needs

Direct symbol queries, function/class queries, caller/callee context, import dependency context, graph and keyword candidate merging, duplicate removal, ranking behavior, context token budget, missing/invalid graph fallback, and existing retrieval regression tests.