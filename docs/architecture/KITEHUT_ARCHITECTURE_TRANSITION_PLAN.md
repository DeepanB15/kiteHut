# KiteHut Architecture Transition Plan (ATP-01)

**Product:** KiteHut — Repository Intelligence & Evidence Engine  
**Mode:** Read-only architecture planning; no implementation performed  
**Planning baseline:** Existing source and tests inspected; tests were not run as part of this document-only task.

## 0. Product direction

KiteHut is a local-first **Repository Intelligence & Evidence Engine**. It is not a general-purpose coding chatbot and not a repository graph database product; it answers questions about a repository and must show why the answer is trustworthy.

> **Graph to understand. Context to reason. Evidence to trust.**

| Pillar | Question it answers | Established here | Not claimed here |
|---|---|---|---|
| **Code Graph** | What exists in this repository, and how is it connected? | Deterministic, source-provenanced symbols and relationships with stable IDs, validation, canonical serialization and bounded traversal (§4.1, §5, §6). | Language coverage beyond Python; runtime/dynamic call graphs; persistence. |
| **Smart Context** | Which source should be read to answer a question? | A composition boundary over existing chunking, retrieval, ranking and optional local embeddings, with graph-derived candidates (§4.2, §7). | A recalled, token-budgeted context product and its recall targets — deferred to the Smart Context integration phase. |
| **Evidence Engine** | Is the claim actually supported by this repository snapshot? | Graph/source evidence contracts, provenance freshness and status mapping (§4.3, §5). | A unified claim-verification product across all existing verdict vocabularies. |

The three pillars are deliberately uneven in this plan. Phase 11 builds the Code Graph foundation and its test evidence only; Smart Context integration and the unified Evidence Engine are follow-on work (§9, §10). Source code remains the ultimate source of truth: the graph is navigation, context is selection, and evidence is proof. None of them may be presented as authority over the file contents they describe.

## 1. Recommendation

Proceed with a Python-first, in-memory Code Graph MVP as a new backend capability. Reuse existing repository discovery, Python AST knowledge, chunks, hybrid retrieval, local embedding provider, and evidence collection through adapters. Do not treat the existing LangGraph workflow as a code graph, and do not replace the agent, MCP, analysis, or findings systems.

The current codebase contains useful but separate capabilities. It does **not** currently provide one canonical graph with stable node and edge IDs, source-backed `CALLS` edges, graph validation, deterministic graph serialization, or NetworkX traversal. Semantic retrieval components exist, but the inspected RAG construction path does not currently wire a vector retriever or pass a query vector. There are also multiple evidence and verdict model families. The transition should consolidate those interfaces incrementally rather than create competing parsers, retrieval systems, or evidence schemas.

| Product pillar | Existing state | ATP-01 target |
|---|---|---|
| Code Graph | Repository inventory, Python AST symbol extraction, import analysis, symbol index, and ProjectMap exist separately. No canonical graph or `CALLS` relationship layer was found. | Add a deterministic, validated, source-provenanced graph and bounded traversal. |
| Smart Context | Chunking, keyword/symbol/vector retrieval components, ranking, context formatting, and local Ollama integration exist. The RAG path's semantic branch is not wired end-to-end. | Combine graph-guided candidates with existing retrieval and ranking; keep local embeddings and LLM integration. |
| Evidence Engine | Finding verification, claim extraction, evidence collection, confidence and truth classification exist in more than one subsystem. | Add graph/source evidence contracts and adapters; preserve current APIs and explicitly map verdict vocabularies. |

## 2. Evidence labels and scope

- **Verified existing** means the inspected source defines the stated class/function or wiring. This is not a claim that the feature passed a fresh runtime test.
- **Partially implemented** means source exists, but inspection found a limitation or incomplete connection that prevents claiming the full ATP capability.
- **New proposed** means no implementation was found in the inspected active backend.
- **Deferred legacy** means retain the capability as a separate existing product surface or historical reference; do not make it a dependency of the Code Graph MVP.

The relevant tests inspected include `backend/tests/test_context_engine.py`, `test_phase4_code_intelligence.py`, `test_phase6_evidence_evaluation.py`, `test_verification_engine.py`, `test_phase8_1_chunking.py` through `test_phase8_6_rag.py`, and `test_review_integration.py`. Test names and coverage noted below are source inspection only; no test suite was run.

## 3. File-level transition matrix

| Existing path | Current responsibility / exact interfaces | Target module | Decision | Reason | Dependencies | Tests / evidence |
|---|---|---|---|---|---|---|
| `backend/app/context/repository/repo_inspector.py` | `RepoInspector.inspect`, `FileInfo`, `RepoStructure`; filesystem inventory, language and directory statistics | `code_graph.discovery` adapter | **REFACTOR** | Reuse inventory facts, but define one graph scan policy. Current inspector skips all hidden directories, `workspace`, and several generated directories, and has a file cap; make exclusions and errors explicit for graph builds. | `pathlib`, `os`, Pydantic | `backend/tests/test_context_engine.py::test_repo_inspector_and_tech_detector` |
| `backend/app/context/repository/tech_detector.py` | `TechDetector.detect`, `find_entry_points`; manifest-based technology and entry-point hints | `smart_context` / ProjectMap integration | **KEEP** | Useful descriptive metadata, not graph truth or source symbol extraction. | `RepoInspector`-style filesystem access | `backend/tests/test_context_engine.py::test_repo_inspector_and_tech_detector` |
| `backend/app/context/code/ast_analyzer.py` | `ASTCodeAnalyzer.parse_file`, `CodeSymbol`, `SymbolType`; Python AST plus regex-style extraction for other supported extensions | `code_graph.python_extractor`; compatibility facade | **REFACTOR** | Python AST is a sound starting point, but current extraction does not recursively model all nested scopes and non-Python regex extraction cannot support precise graph provenance. Make the new extractor canonical and adapt this interface to it rather than keeping two parsers. | Python `ast`, Pydantic, `SymbolIndex` | `backend/tests/test_context_engine.py::test_ast_code_analyzer_python`; `test_phase4_code_intelligence.py::test_ast_analyzer_python` |
| `backend/app/context/code/import_analyzer.py` | `ImportAnalyzer.parse_python_imports`, `build_graph`; `ImportStatement`, `ImportGraph`, cycle detection and external-package extraction | `code_graph.relationships`; compatibility facade | **REFACTOR** | Python imports have AST line locations and useful resolution logic; non-Python parsing is regex-based. Move canonical import resolution into graph relationship extraction, then adapt `ImportGraph` consumers from graph edges to avoid duplicate parsers. | Python `ast`, repository file inventory | `backend/tests/test_context_engine.py::test_import_analyzer_and_circular_detection` |
| `backend/app/context/code/symbol_index.py` | `SymbolIndex` name/file/type search and summary over `CodeSymbol` | `code_graph.queries` adapter | **REFACTOR** | Preserve existing lookup behavior while querying `SymbolNode` IDs and qualified names. The current index is not itself a graph and symbols have no graph ID. | `CodeSymbol`, Pydantic | `backend/tests/test_context_engine.py::test_symbol_index_and_snippet_retriever`; `test_phase4_code_intelligence.py::test_symbol_index_exists` |
| `backend/app/context/code/intelligence_engine.py` | `CodeIntelligenceEngine.scan`, `find_symbol`, `get_file_symbols` | Legacy API facade over `code_graph` | **REFACTOR** | Keep callers stable, but eliminate its independent recursive scan and duplicate symbol index once graph APIs can provide equivalent results. | `ASTCodeAnalyzer`, `ProjectMapBuilder` import, `CodeSymbol` | `backend/tests/test_phase4_code_intelligence.py::test_intelligence_engine_scans_py_file`, `test_intelligence_engine_find_symbol`, `test_intelligence_engine_empty_repo` |
| `backend/app/context/project_map/project_map.py` | `ProjectMapBuilder.build`, `_classify_layers`; returns `ProjectMap`, `SymbolIndex`, and `ImportGraph` | `smart_context` / compatibility adapter | **REFACTOR** | Keep technology/layer summaries, but derive symbols and imports from the canonical graph rather than re-reading and re-parsing source. It is descriptive project context, not a graph runtime. | `RepoInspector`, `TechDetector`, `ASTCodeAnalyzer`, `ImportAnalyzer`, `SymbolIndex` | Indirectly exercised by `backend/tests/test_context_engine.py`, `test_phase4_code_intelligence.py`, and `test_phase2_tools.py` |
| `backend/app/chunking/model.py`, `python_chunker.py`, `repository_chunker.py` | `CodeChunk`, `ChunkList`, `chunk_python_file`, `chunk_file`, `chunk_repo`; source chunks, hashes, symbol labels, and line spans | `smart_context` | **KEEP** | Reuse chunk IDs/content hashes and line metadata for retrieved context. A chunk is not a graph node; maintain explicit chunk-to-file/symbol references. | Python `ast`, Pydantic | `backend/tests/test_phase8_1_chunking.py` |
| `backend/app/embedding/provider.py`, `local_provider.py`, `indexer.py`, `record.py`, `store.py`, `validation.py` | `EmbeddingProvider`, `OllamaEmbeddingProvider`, `EmbeddingIndexer`, `EmbeddingRecord`, `EmbeddingStore`; local embeddings and JSONL persistence | `smart_context` | **KEEP** | Preserve local-first provider and store. Graph construction must not require Ollama or embedding availability. | Existing embedding provider dependency and JSONL store | `backend/tests/test_phase8_2_embeddings.py` |
| `backend/app/retrieval/retrieval.py`, `local_index.py`, `similarity.py` | `VectorRetrieval`, `LocalVectorIndex`, `cosine_similarity`; local vector search primitives | `smart_context` | **KEEP** | Reuse semantic retrieval primitives, but report unavailable vectors distinctly rather than silently presenting keyword-only results as semantic retrieval. | Chunk IDs, embeddings | `backend/tests/test_phase8_3_retrieval.py`, `test_phase8_4_hybrid.py` |
| `backend/app/retrieval/hybrid/retrieval.py` | `HybridRetriever`, `keyword_retrieve`, `symbol_retrieve`, `RetrievalCandidate`, `HybridRetrievalResult`; fusion and deduplication | `smart_context` | **KEEP** | This is the existing keyword/symbol/semantic candidate-fusion surface. Add graph candidates at the orchestration/ranking boundary, not a second hybrid retriever. | Chunker, vector retrieval, local index | `backend/tests/test_phase8_4_hybrid.py` |
| `backend/app/context/ranking.py` | `ContextRanker.rank`, `ContextRankingConfig`, `RankedContext`, `RankingBreakdown`; deterministic score, deduplication, diversity and character budget | `smart_context` | **REFACTOR** | Extend ranking with an optional, separately inspectable graph-relevance signal; preserve current ranking and budget behavior when no graph is supplied. | `HybridRetrievalResult`, `CodeChunk` | `backend/tests/test_phase8_5_context.py`, `test_phase8_6_rag.py` |
| `backend/app/rag/context_builder.py`, `prompt_builder.py`, `llm_provider.py`, `pipeline.py` | `ContextBuilder`, `PromptBuilder`, `RagLlmProvider`, `RagPipeline`; formats context and invokes local LLM | `smart_context` integration | **REFACTOR** | Keep this integration path, but have it consume the unified retrieved-context contract. Inspection found `_make_vector_retriever()` returns `None` and the pipeline passes `query_vector=None`, so semantic retrieval is not active in this path today. | Hybrid retrieval, ranking, chunk metadata, local Ollama | `backend/tests/test_phase8_6_rag.py`, `test_phase8_integration.py` |
| `backend/app/verification/extractors/claim_extractor.py`, `collectors/evidence_collector.py` | `ClaimExtractor.extract_claims`, `EvidenceCollector.collect_evidence_for_claims`; finding-derived claims and source/project-map evidence collection | `evidence` adapters | **REFACTOR** | Reuse claim extraction and file reading, while mapping their output to typed atomic claims and graph/source evidence. | `Finding`, `ProjectMap`, `SymbolIndex`, `ImportGraph`, source files | `backend/tests/test_verification_engine.py::test_claim_extractor_and_evidence_collector` |
| `backend/app/verification/models/claim.py`, `models/evidence.py`, `models/truth.py`, `verification_engine.py` | `ExtractedClaim`, `EvidenceItem`, `VerificationVerdict`, `VerificationEngine.verify_finding`, `verify_report`; statuses include `TRUE`, `PARTIALLY_TRUE`, `UNCERTAIN`, `FALSE` | `evidence` compatibility adapters | **REFACTOR** | Preserve existing public findings flow. Map statuses explicitly to `SUPPORTED`, `UNSUPPORTED`, `INCONCLUSIVE`; do not reinterpret a legacy `FALSE` as `UNSUPPORTED` without considering evidence completeness. Existing `EvidenceItem` IDs are generated, not deterministic graph IDs. | Intelligence findings, evidence collector, truth classifier and scoring | `backend/tests/test_verification_engine.py` |
| `backend/app/review/finding.py`, `review_engine.py`, `evidence_verifier.py`, `evidence_quality_engine.py` | `Finding`, `Evidence`, `ReviewEngine.review_repo`, `EvidenceVerifier.verify`; rule-based review and snippet/rule rechecks | Existing review subsystem; `evidence` adapter | **KEEP** | This is a separate deterministic rule-review pipeline with its own status/quality vocabulary. Reuse its source-verification lessons; do not merge it into the graph model or replace its finding contract in the MVP. | Review rules, repository files | `backend/tests/test_phase5_review_engine.py`, `test_phase6_evidence_evaluation.py`, `test_review_integration.py` |
| `backend/app/graph/state.py`, `backend/app/graph/workflow.py` | `AnalysisState`, `create_workflow`, compiled LangGraph orchestration nodes | Existing analysis orchestration | **KEEP** | This is a workflow/state-machine graph for analysis execution, not a source-code graph. The name overlap is not a reason to relocate or reuse it. | LangGraph, agent/analysis engines | `backend/tests/test_phase5_integration.py` through `test_phase10_integration.py` |
| `backend/app/engines/blast_radius_engine.py` | `analyze_blast_radius`, `_build_dependency_graph`, `_calculate_radius`; heuristic import scan and keyword-based affected-file selection | Future `code_graph.queries` adapter | **DEFER** | Preserve existing scoring/report surface for parity. Its line-based import parsing and keyword search are not equivalent to verified graph traversal; migrate only after graph query behavior is validated. | `ScoredFinding`, `BlastRadius`, filesystem | `backend/tests/test_action_engine.py`, `test_prioritization_and_scoring.py` (no dedicated graph test found) |
| `backend/app/agent/context/manager.py`, `agent/runtime/`, `agent/router/`, `agent/state/` | `AgentContextManager`; agent planning, tool routing, execution and state models | `smart_context` / `evidence` adapters | **KEEP** | Agent remains a consumer/integration layer. Supply bounded context and evidence through typed interfaces; do not place graph traversal or extraction logic inside the agent loop. | Agent state, tools, LLM provider | `backend/tests/test_agent_runtime.py`, `test_phase9_1_agent_state.py` through `test_phase9_4_loop.py` |
| `backend/app/tools/phase2_tools.py`, `tools/registry.py` | `FindSymbolTool`, `GetRepoStructureTool`, `RunAnalysisTool`, `ToolRegistry`, `create_default_tool_registry` | Thin graph/context/evidence tools | **REFACTOR** | Keep permission-aware tools and registry; add graph/context/evidence tools as adapters with bounded, read-only operations. Replace duplicate `ProjectMapBuilder` calls only after compatibility tests. | `ProjectMapBuilder`, `SymbolIndex`, permission manager | `backend/tests/test_phase2_tools.py`, `test_tools.py` |
| `backend/app/mcp/server.py` | `RepoLensMCPServer`, `_register_all`, `_wrap_tool`, `get_mcp_server`; exposes the registry over MCP | Integration layer | **KEEP** | Continue registering tools from the shared registry. MCP must not implement an independent graph or evidence API. | FastMCP, `ToolRegistry`, permissions | `backend/tests/test_phase2_tools.py`, `test_review_integration.py::TestReportingDoesNotBreakMCP` |
| `frontend/src/api/repositories.ts`, `frontend/src/pages/RepositoryPage.tsx`, `FindingsPage.tsx`, `frontend/src/types/repository.ts` | Repository/analysis and findings API calls and screens; no graph browser or Smart Context screen was found in inspected frontend source | Future product UI | **DEFER** | Existing UI is analysis/findings oriented. The backend contracts should stabilize first; no frontend implementation belongs in Phase 11. | Existing API types/hooks and backend endpoints | No Code Graph or context-specific frontend tests found in inspected source |
| `archive/repolens-v2/repo-lens/packages/analyzers/core.py`, `python.py`, `packages/graph/store.py`, `queries.py`, `impact.py`, `packages/evidence/models.py` | Archived `PythonAnalyzer`, `GraphStore`, `GraphQueryEngine`, `ImpactEngine`, and `EvidenceItem` prototypes | Historical reference only | **DEFER** | Python analyzer is AST-based but relationship extraction is incomplete; persistence is DB-session-oriented and commits per item; archived `ImpactEngine.analyze` returns placeholder values. It is not the active backend source of truth and must not be copied wholesale. | Archived SQLAlchemy models/database and archived API | `archive/repolens-v2/repo-lens/docs/IMPLEMENTATION_AUDIT.md` is a historical audit, not an active test |
| `backend/app/code_graph/` (not present) | No canonical graph package found | Code Graph | **NEW** | Own stable IDs, typed nodes/edges, extraction/build/validation, JSON and traversal. | `pathlib`, `ast`, Pydantic; NetworkX dependency decision in Task 11.8 | New `backend/tests/code_graph/` suite |
| `backend/app/smart_context/` (not present) | No single graph-aware context contract found | Smart Context | **NEW** | Compose existing retrieval/ranking/chunk and graph query interfaces without duplicating them. | `code_graph`, `chunking`, `retrieval`, `embedding`, existing ranker | New `backend/tests/smart_context/` suite (subsequent integration scope) |
| `backend/app/evidence/` (not present) | No unified graph-plus-source evidence contract found | Evidence Engine | **NEW** | Define claim/evidence/verdict contracts and adapters; Phase 11 only provides graph/source foundations, not a full claim-verification product. | `code_graph`, source readers, existing verification adapters | New `backend/tests/evidence/` contract tests (later integration scope) |

## 4. Target package boundaries

### 4.1 Code Graph

Proposed package: `backend/app/code_graph/`.

| File | Responsibility |
|---|---|
| `models.py` | Pydantic contracts and enums for graph, source spans, build/validation reports, and extractor diagnostics. |
| `discovery.py` | Repository-root validation, deterministic relative-path discovery, exclusion policy, content reads/hashes, and explicit file-read diagnostics. |
| `python_extractor.py` | Python AST declarations, lexical containment, import references, and syntactic call sites with source spans. |
| `relationships.py` | Resolve deterministic `CONTAINS`, `DEFINES`, `IMPORTS`, and conservative `CALLS` edges from discovered files and extraction results. |
| `builder.py` | Coordinate discovery and extraction; return a graph plus errors/warnings without hiding failures. |
| `validation.py` | Check ID uniqueness, edge endpoints/types, source paths/spans, node/file consistency, and graph invariants. |
| `serialization.py` | Canonical, versioned JSON serialization and deserialization with stable ordering. |
| `graph_runtime.py` | Optional NetworkX projection of the validated graph, built in memory. |
| `queries.py` | Symbol lookup, callers, callees, imports/dependents, and bounded traversal APIs returning source references. |

Do not persist graph tables in a database for the MVP. The canonical graph is a validated Pydantic model; NetworkX is a runtime/query representation. Existing `backend/app/graph/` remains the separate LangGraph orchestration package.

### 4.2 Smart Context

Proposed package: `backend/app/smart_context/`.

| File | Responsibility |
|---|---|
| `models.py` | `ContextCandidate`, `RetrievedContext`, candidate origin, score breakdown and retrieval diagnostics. |
| `graph_candidates.py` | Translate graph query results into candidate file/symbol/chunk references. |
| `retriever.py` | Orchestrate existing keyword/symbol/vector retrieval plus graph-derived candidates; avoid reimplementing retrieval algorithms. |
| `ranker.py` | Adapt existing `ContextRanker` to combine normalized retrieval and graph relevance with inspectable weights. |
| `context_builder.py` | Build token/character-bounded source context with paths, line ranges and provenance. |
| `evaluation.py` | Fixture query set and recall/precision/budget measurements for retrieval changes. |

The existing embedding provider and local Ollama integration remain optional components. Graph construction and keyword/symbol retrieval must work with Ollama unavailable.

### 4.3 Evidence

Proposed package: `backend/app/evidence/`.

| File | Responsibility |
|---|---|
| `models.py` | Atomic claim, graph evidence, source evidence, verification verdict and provenance contracts. |
| `claim_extractor.py` | Adapt existing finding-derived claim extraction; preserve the distinction between an observed claim and an inferred one. |
| `collectors.py` | Collect graph references and source snippets against the same repository snapshot. |
| `verifier.py` | Verify exact source claims, graph relationship claims and provenance freshness; report unsupported only when evidence coverage is sufficient. |
| `adapters.py` | Map existing verification and review model/status families to the new contract without changing their public behavior. |

Do not count graph presence alone as proof that a source claim is true. Every graph-derived relationship must carry the edge-type-appropriate provenance and source digest used to build it. `IMPORTS` and `CALLS` must point to the exact statement span; lexical `CONTAINS` and `DEFINES` point to the child declaration span; repository-to-file `CONTAINS` points to the discovered relative path and file hash and does not require a source-code span. A changed/missing source must make the evidence stale or inconclusive, never silently supported.

## 5. Core data contracts

All source paths are repository-relative POSIX paths in serialized data. Line numbers are 1-based and inclusive. Absolute root paths may be included as non-identity display metadata, but never participate in stable IDs.

**Repository identity and ID algorithm:** accept an explicit stable `repository_id` when the caller has one. Otherwise, normalize the Git `origin` URL (convert HTTP(S) and SCP-style SSH forms to `https://host/path`; strip credentials, lowercase the host, omit default ports/query/fragment, remove a trailing `.git`, preserve owner/repository path case) and set `repository_id` to `repo:v1:` plus the lowercase hexadecimal SHA-256 of the UTF-8 bytes of canonical JSON `{"origin": normalized_origin}`. If there is no origin but a caller-supplied stable repository key, use `repo:v1:` plus SHA-256 of canonical JSON `{"key": normalized_key}`. If neither exists, derive a clearly snapshot-scoped identity as `snapshot:v1:` plus SHA-256 of canonical JSON containing the sorted pairs of normalized repository-relative path and SHA-256 of each file's raw bytes. Do not claim that the fallback snapshot identity remains stable when files change.

Generate all IDs as `kind:v1:` plus lowercase hexadecimal SHA-256 of UTF-8 canonical JSON identity inputs, serialized with sorted keys, compact separators, UTF-8 without ASCII escaping, normalized Unicode (NFC), and no absolute paths. Normalize relative paths to `/`, collapse `.` segments, reject `..` escapes, normalize Unicode to NFC, and preserve case. File identity inputs are `repository_id` and normalized relative path. Symbol identity inputs are `repository_id`, relative path, qualified name, symbol kind, and a deterministic AST-preorder occurrence ordinal among identical declarations in that scope. Edge identity inputs are `repository_id`, relationship kind, source ID, target ID, and a provenance discriminator (the source relative path and line/column coordinates for statement-backed edges; the relationship kind and endpoint pair for structural edges). Content hashes and source coordinates remain provenance, not repository identity; symbol IDs do not claim stability across rename or ambiguous duplicate insertion.

| Model | Proposed core fields | Contract notes |
|---|---|---|
| `RepositoryNode` | `id`, `repository_id`, `name`, optional `root_path`, optional `revision`, `source_digest` | `source_digest` identifies the graph input snapshot; root path is not a portable identifier. |
| `FileNode` | `id`, `repository_id`, `relative_path`, `language`, `content_hash`, `line_count`, `byte_size` | Canonical path uses `/`; file identity is stable for the same repository and relative path. |
| `SymbolNode` | `id`, `repository_id`, `file_id`, `relative_path`, `name`, `qualified_name`, `kind`, optional `parent_id`, `start_line`, `end_line`, `source_hash`, `extractor` | Python declaration kinds include class, function, async function and method; nested lexical scopes are represented explicitly. |
| `GraphEdge` | `id`, `repository_id`, `source_id`, `target_id`, `kind`, `provenance_kind`, optional `source_file`, `start_line`, `end_line`, `confidence`, `resolution`, `extractor`, optional `source_hash`, `metadata` | `kind` is one of `CONTAINS`, `DEFINES`, `IMPORTS`, `CALLS`. Provenance is edge-type-specific: structural `CONTAINS` (repository-to-file) references the discovered relative path and file hash, structural lexical `CONTAINS` and `DEFINES` reference the declared child's AST span and file hash, and statement-backed `IMPORTS`/`CALLS` reference the exact import/call-site span and file hash. Only statement-backed edges require a source-code statement span. |
| `CodeGraph` | `schema_version`, `repository`, sorted `files`, sorted `symbols`, sorted `edges`, `source_digest` | Canonical graph payload; only valid, endpoint-backed edges appear in this collection. |
| `GraphBuildResult` | optional `graph`, `status` (`complete`, `partial`, `failed`), `coverage`, counts, `errors`, `warnings`, `truncated`, `unresolved_imports`, `unresolved_calls` | `complete` means exhaustive discovery and successful processing of the configured Python scope; unsupported languages are listed in coverage and do not imply semantic analysis of the whole repository. Expected unresolved/ambiguous relationships do not alone make a build partial. Syntax errors, unreadable in-scope files, or file-limit truncation make a usable, validated graph `partial`. `failed` means no coherent validated graph can be produced (for example an invalid/missing root, fatal scan error, or graph validation failure) and carries no graph. |
| `GraphValidationResult` | `valid`, `errors`, `warnings`, `checked_nodes`, `checked_edges` | Validation errors identify the affected node/edge and violated invariant. |
| `GraphEvidence` | `repository_id`, `graph_digest`, `edge_id`, `source_node_id`, `target_node_id`, `relationship`, provenance kind, optional `source_file`, optional `start_line`/`end_line`, `source_hash`, `resolution`, `confidence` | Graph evidence links to exactly the edge and its edge-type-specific provenance. Statement-backed edges require a source span; structural repository-to-file containment uses discovered path/file hash and has no source-code span. |
| `SourceEvidence` | `repository_id`, `relative_path`, `start_line`, `end_line`, `snippet`, `content_hash`, `revision`, `evidence_kind`, `confidence` | Snippet must be read/validated against the current source snapshot before claiming support. |
| `EvidenceClaim` | `id`, `text`, `claim_type`, `subject`, optional `object`, `origin`, `source_finding_id` | One atomic proposition per claim; keep extraction provenance and distinguish observed from inferred claims. |
| `VerificationResult` | `claim_id`, `status`, `confidence`, `explanation`, `graph_evidence`, `source_evidence`, `limitations` | `status` is `SUPPORTED`, `UNSUPPORTED`, or `INCONCLUSIVE`; absent evidence alone is not proof of falsity. |
| `ContextCandidate` | `id`, `repository_id`, `relative_path`, optional `symbol_id`, optional `chunk_id`, `start_line`, `end_line`, `content`, `retrieval_score`, `graph_score`, `score_breakdown`, `source_hash` | Preserve chunk and symbol identity independently; normalize score range and ranking weights explicitly. |
| `RetrievedContext` | `query`, `repository_id`, `graph_digest`, `candidates`, `context_text`, `estimated_tokens`, `token_budget`, `diagnostics` | Output includes selected source citations and retrieval mode/status, including when semantic retrieval is unavailable. |

IDs should be deterministic for an unchanged logical input, and JSON output must be byte-stable for the same graph after canonical sorting. IDs should not claim stability across a symbol rename or ambiguous duplicate insertion. Each serialized graph records a schema version so future changes are explicit.

## 6. Code Graph MVP and relationship certainty

### Deterministic in the MVP

- Discover files with a fixed, tested exclusion policy and canonical repository-relative paths. Determine `repository_id` using the precedence and SHA-256 canonicalization rule in Section 5; absolute paths must never affect repository or entity IDs.
- Parse supported Python files with `ast.parse`; report unreadable files and syntax errors explicitly.
- Extract class/function/async-function/method declarations, including nested classes and nested functions, with qualified scope and AST source spans.
- Link repository-to-file containment, lexical parent-to-child containment, and file-to-symbol definitions. Structural repository-to-file containment cites discovered relative path and file hash; lexical containment and definitions cite the child declaration span and source hash. These edges are derived from structure and do not require a separate source statement.
- Extract Python import statements and their line spans. Resolve a local import only when its module/file mapping is unambiguous in the scanned repository.
- Validate that every edge has the provenance appropriate to its edge type, endpoints exist, and any required source span points into the recorded file snapshot.
- Serialize sorted nodes and edges deterministically.
- Traverse validated edges with bounded depth and return IDs plus source references.

### Conservative or uncertain

- A syntactic `ast.Call` site is deterministic; resolving its callee to a unique in-repository symbol is not always deterministic in Python.
- `CALLS` resolution is limited to a deliberately small, documented static subset: a bare-name call may resolve only when there is exactly one in-repository target in the applicable module/lexical scope and no parameter, local assignment, import alias, `global`/`nonlocal`, or other binding can shadow it; an explicitly imported alias may resolve only when its import target is itself unique and unambiguous. These conditions are sufficient only for the supported static cases; they do not prove runtime dispatch.
- Extracting a call site's syntax is deterministic, but any call outside the supported subset—including all attribute calls such as `self.method()`/`cls.method()` in the MVP, dynamic dispatch, arbitrary receivers, monkey-patching, reflection, `getattr`, runtime-generated functions, unresolved star imports, or runtime import hooks—must be reported as unresolved. If multiple static targets remain, report ambiguous. Do not emit a resolved `CALLS` edge for either state and do not invent targets.
- Python package/import semantics can be affected by namespace packages, `sys.path`, relative-import context, and platform-specific casing. Preserve unresolved/ambiguous imports as diagnostics rather than false local edges.
- External imports are metadata/diagnostics in the MVP, not graph edges to synthetic nodes. This keeps the graph endpoint invariant simple.
- JS/TS/Go regex extraction in current code is not the basis for MVP graph claims. Non-Python files may be discovered as `FileNode`s but have no claimed symbol/call support until a language parser is separately planned.

### Runtime and queries

Use the standard-library `ast` for extraction and Pydantic for contracts. NetworkX is not currently listed in `backend/pyproject.toml`; add it only as a deliberate Phase 11 runtime dependency when implementing Task 11.8, and keep the serialized Pydantic graph authoritative. The NetworkX projection must not add unsupported edges or mutate canonical model data.

Expose small query functions: `find_symbols(name_or_qualified_name)`, `callers(symbol_id, depth=1)`, `callees(symbol_id, depth=1)`, `imports(file_id, depth=1)`, and `dependents(file_id, depth=1)`. Require bounded depth, visited-node tracking and deterministic result ordering.

## 7. Integration boundaries

1. **Project discovery:** graph discovery reuses existing repository inspection where its policy is suitable, but defines an explicit source/ignore policy and content hashes. `ProjectMapBuilder` becomes a compatibility consumer of graph outputs; it continues producing technology and layer summaries.
2. **Smart Context:** retrieve existing chunks using `HybridRetriever`; graph queries contribute related symbols/files as candidates. Resolve candidate code through existing chunks where possible; preserve the graph node ID and source span on each candidate.
3. **Ranking:** retain `ContextRanker`'s current retrieval score, deduplication and budget behavior. Add a separately reported graph signal. A starting formula may be `combined = w_retrieval * normalized_retrieval + w_graph * normalized_graph`; weights require labeled-fixture evaluation and are not fixed by this plan.
4. **Semantic retrieval:** reuse `EmbeddingProvider`, `EmbeddingStore`, `LocalVectorIndex`, and `VectorRetrieval`. Wire query embedding explicitly in the RAG integration and report when it is unavailable. Never label keyword-only output as semantically retrieved.
5. **Evidence:** evidence claims reference a graph digest and source digest. `GraphEvidence` resolves through `GraphEdge` to its edge-type-specific provenance: statement spans for imports/calls, child declaration spans for lexical containment/definitions, and discovered path/file hash for repository-to-file containment. `SourceEvidence` independently verifies the current source. Stale graph/source digests result in stale or inconclusive evidence.
6. **Legacy verification:** adapters map `ExtractedClaim`/`EvidenceItem`/`VerificationVerdict` and review `Finding`/`Evidence`/`VerificationStatus` to the new contracts. Keep legacy status and API payloads unchanged until consumers migrate.
7. **Agents and MCP:** agents, tools and MCP invoke public service interfaces. Add bounded read-only graph queries and Smart Context/evidence tools through `ToolRegistry`; do not expose mutable graph internals or trigger full builds on every tool call without an explicit cache/snapshot policy.
8. **LangGraph:** leave `backend/app/graph/workflow.py` as analysis orchestration. If useful later, orchestration may call the Code Graph service; graph nodes/edges do not become LangGraph states.
9. **Frontend:** defer graph browsing and context/evidence UI until backend contracts and endpoint behavior are stable. Existing repository and findings pages remain unchanged in this phase.

## 8. Testing strategy and quality gates

All thresholds below are **proposed acceptance criteria**, not measured current performance.

| Gate | Proposed measurable criterion |
|---|---|
| Python AST extraction | Fixture declarations (including nested class/function and async cases) match expected qualified names, types and exact inclusive line ranges; malformed files produce diagnostics and no fabricated symbols. |
| Imports | Every resolved local import points to an existing file; relative imports, package `__init__.py`, aliases, external imports, missing modules, cycles and ambiguous candidates have explicit expected results. |
| Calls | Every emitted `CALLS` edge has a unique supported static resolver result and call-site span. Attribute/dynamic/ambiguous fixture calls produce no resolved edge and at least one unresolved/ambiguous diagnostic. |
| Duplicate symbols | Same-name declarations in different files/scopes produce distinct IDs and both remain searchable; duplicate declarations in one scope are stable and diagnosed where needed. |
| Validation | 100% of accepted graphs have unique node/edge IDs, zero dangling endpoints, valid source paths and in-range 1-based spans; all injected invalid cases fail with a targeted diagnostic. |
| Determinism | Building and serializing the same fixture twice (including different file enumeration order) yields identical canonical JSON and IDs. |
| Provenance | Every symbol and statement-backed edge resolves to an existing file, valid inclusive span, and matching source hash in the build snapshot. Structural edges have the edge-type-specific path/file-hash or child-declaration provenance defined in Section 5. |
| Build status | A build is `complete` only when discovery was exhaustive and every in-scope supported source file was read and parsed without errors; unsupported-language coverage is reported explicitly. A usable graph with syntax errors, unreadable files, or file-limit truncation is `partial`. Missing/invalid root, fatal scan failure, or graph-validation failure is `failed`; all states carry explicit diagnostics and a failed result cannot be presented as complete. |
| Traversal | Caller/callee/import/dependent queries return deterministic bounded results, terminate on cycles, respect depth limits, and preserve edge source evidence. |
| Smart Context (future integration phase) | On a labeled fixture query set, expected-symbol/file recall@5 is at least 0.80; deduplicated output stays within the configured token budget; each item cites path and lines. Track keyword/symbol/vector/graph score components separately. This is not a Phase 11 gate. |
| Sample repository benchmark | Initially document measured scan/build/validate time for a generated fixture of 1,000 Python files and up to 20,000 symbols, excluding environment setup; record hardware, Python version, fixture generation and results. The 10-second target is an optimization goal for follow-up, not a Phase 11 correctness gate. |
| Regression | Existing phase 4, phase 6, phase 8 retrieval/RAG, agent/tool and MCP tests continue to pass after adapter work. Do not change legacy response shapes without an explicit migration. |

Fixture coverage must include nested classes/functions, imports (absolute/relative/alias/star), duplicate names, syntax errors, missing source, cycles, ambiguous imports/calls, `self`/`cls` calls, external dependencies, stable serialization, source modifications after graph build, and a small sample repository with labeled expected queries.

## 9. Deferred scope

- Language-specific semantic extraction beyond Python.
- Dynamic/runtime call graph construction.
- Persistent graph database or cross-session graph service.
- Automatic frontend graph visualization.
- Agent-driven code edits, remediation or autonomous graph mutations.
- Replacing all legacy verification and review models in one change.
- Treating archived RepoLens v2 code as production-ready implementation.

## 10. Decision

**Recommendation: approve Phase 11 planning only, then implement the graph foundation behind existing interfaces.** Do not advertise all three flagship modules as complete after Phase 11: the requested tasks establish the Code Graph and its test evidence; Smart Context integration and the unified Evidence Engine require follow-on implementation and acceptance gates.
