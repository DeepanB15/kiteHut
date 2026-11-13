# Phase 11 Implementation Plan — Code Graph MVP

**Status:** Proposed; not implemented  
**Scope:** Python-first, local, in-memory Code Graph foundation  
**Prerequisite:** Approval of ATP-01 scope and contracts  
**Non-goals:** Application startup, database persistence, frontend work, autonomous edits, broad language support, or replacement of the LangGraph workflow

## 1. Target layout

Add the following active backend package and tests without moving or restructuring existing frontend/backend code:

```text
backend/
  app/
    code_graph/
      __init__.py
      models.py
      discovery.py
      python_extractor.py
      relationships.py
      validation.py
      builder.py
      serialization.py
      graph_runtime.py
      queries.py
  tests/
    code_graph/
      __init__.py
      conftest.py
      test_models.py
      test_discovery.py
      test_python_extractor.py
      test_relationships.py
      test_validation.py
      test_builder.py
      test_serialization.py
      test_queries.py
    fixtures/
      code_graph/
        sample_project/
          ...
```

The fixture is a small, purpose-built repository committed with the tests. Do not use the active KiteHut repository as a mutable test fixture. Keep `backend/app/graph/` unchanged: it is the existing LangGraph analysis workflow.

## 2. Tasks

Tasks are dependency ordered. The listed interfaces are proposed public/internal contracts; keep names consistent as implementation proceeds.

### Task 11.1 — Graph data models

**Files**
- Add `backend/app/code_graph/__init__.py`
- Add `backend/app/code_graph/models.py`
- Add `backend/tests/code_graph/__init__.py`
- Add `backend/tests/code_graph/test_models.py`

**Interfaces**
- `NodeKind`, `SymbolKind`, `EdgeKind`, `ResolutionKind`, `EvidenceConfidence`, `ProvenanceKind`
- Pydantic models: `RepositoryNode`, `FileNode`, `SymbolNode`, `GraphEdge`, `CodeGraph`, `GraphBuildResult`, `GraphValidationResult`
- `GraphBuildResult.graph` is present for `complete` and valid `partial` builds; it is `None` for `failed` builds. A failed result always includes a fatal error diagnostic.
- Internal source records: `SourceFile`, `SymbolDeclaration`, `ImportReference`, `CallSite`
- Shared path and span validation: repository-relative POSIX paths; 1-based inclusive spans
- `GraphBuildStatus`: `complete`, `partial`, or `failed`; `GraphBuildResult` also carries per-language coverage, `truncated`, errors, warnings, and unresolved/ambiguous relationship diagnostics.

**Tests**
- Required/optional fields, enum serialization, invalid ranges, source hash formats and model round trips.
- Distinct symbols for duplicate names; stable canonical identity material independent of absolute root path.
- `CodeGraph` schema version and default collection behavior.
- Build-status consistency: `complete` requires exhaustive discovery and successful processing of every in-scope supported source file; a usable graph with syntax errors, unreadable files, or file-limit truncation is `partial`; invalid/missing root, fatal scan failure, or graph validation failure is `failed`.

**Acceptance**
- Models validate through the installed Pydantic v2 API.
- Every source-derived entity has repository identity and provenance fields.
- The model contract does not depend on NetworkX or database types.
- Repository identity precedence: use an explicit stable `repository_id` when supplied; otherwise normalize Git `origin` (convert HTTP(S) and SCP-style SSH forms to `https://host/path`; strip credentials, lowercase host, omit default ports/query/fragment, remove trailing `.git`, preserve owner/repository path case) and compute `repo:v1:` + lowercase SHA-256 hex of canonical UTF-8 JSON `{"origin": normalized_origin}`. If there is no origin but a caller-supplied stable repository key, compute `repo:v1:` + SHA-256 hex of canonical JSON `{"key": normalized_key}`; if neither exists, compute `snapshot:v1:` + SHA-256 hex of canonical JSON containing the sorted `[relative_path, raw_file_bytes_sha256]` pairs. The snapshot fallback is deliberately not stable across file changes. Absolute paths are never inputs.
- Canonical JSON uses sorted keys, compact separators, UTF-8 without ASCII escaping, normalized Unicode (NFC), and no absolute paths. Normalize relative paths to `/`, collapse `.` segments, reject `..` escapes, normalize Unicode to NFC, and preserve case. Node/edge IDs are `kind:v1:` + lowercase SHA-256 hex of canonical JSON identity inputs: files use repository ID + normalized relative path; symbols use repository ID + path + qualified name + kind + deterministic AST-preorder same-scope occurrence ordinal; edges use repository ID + kind + source ID + target ID + provenance discriminator. For statement edges, the discriminator is the source relative path and line/column coordinates; for structural edges, it is the kind and endpoint pair. Content hashes and source coordinates remain provenance, not repository identity.
- Edge provenance is type-specific: repository-to-file `CONTAINS` records the discovered relative path and file hash; lexical parent-to-child `CONTAINS` and file-to-symbol `DEFINES` record the child declaration AST span and file hash; `IMPORTS` and `CALLS` record the exact import/call-site span and file hash. Only statement-backed edges require a source-code span.
- `GraphEdge` includes `provenance_kind` and the path/hash or statement/declaration span fields required by its relationship type; validators must not require a statement span for repository-to-file `CONTAINS`.

### Task 11.2 — Repository and file discovery

**Files**
- Add `backend/app/code_graph/discovery.py`
- Add `backend/tests/code_graph/test_discovery.py`
- Add fixture files under `backend/tests/fixtures/code_graph/sample_project/`

**Interfaces**
- `RepositoryScanner(root_path, exclude_dirs=..., max_files=...)`
- `discover() -> list[SourceFile]`
- Explicit error/diagnostic records for missing root, unreadable file and file-limit truncation

**Tests**
- Deterministic sorted relative paths; nested directories; recognized and unknown extensions; hidden/generated directories; binary/unreadable content; missing root; file cap diagnostics.
- Confirm each discovered file has content hash, byte size and line count.

**Acceptance**
- Paths never escape the root and serialize with `/`.
- Exclusions are explicit and documented; ignored files are not silently counted as parsed.
- Repeated discovery of unchanged input returns the same file identities and ordering.
- File-limit truncation is reported distinctly and makes the eventual graph build `partial`, not complete.

### Task 11.3 — Python symbol extraction

**Files**
- Add `backend/app/code_graph/python_extractor.py`
- Add `backend/tests/code_graph/test_python_extractor.py`
- Extend `backend/tests/fixtures/code_graph/sample_project/`

**Interfaces**
- `PythonAstExtractor.extract(source_file: SourceFile) -> PythonFileAnalysis`
- `PythonFileAnalysis` includes symbol declarations plus import and call-site records for later relationship resolution.

**Tests**
- Modules, classes, methods, functions, async functions, nested classes/functions, decorators, annotations, duplicate names in separate scopes, exact end lines and empty source.
- Syntax-error fixture returns an explicit parse diagnostic and no invented symbols.
- All spans are 1-based inclusive and source-backed.

**Acceptance**
- Every supported Python declaration is extracted recursively with deterministic qualified scope and parent reference.
- A syntax-error file does not masquerade as an empty successful analysis.
- Unsupported languages are not passed through regex and represented as semantically analyzed.

### Task 11.4 — Relationship extraction and resolution

**Files**
- Add `backend/app/code_graph/relationships.py`
- Add `backend/tests/code_graph/test_relationships.py`
- Extend fixture repository for import and call cases

**Interfaces**
- `RelationshipExtractor.extract_containment(files, analyses) -> list[GraphEdge]`
- `resolve_imports(files, analyses) -> RelationshipResolution`
- `resolve_calls(files, analyses) -> RelationshipResolution`
- `RelationshipResolution` includes edges and explicit unresolved/ambiguous diagnostics.

**Tests**
- `CONTAINS` for repository/file and lexical parent/child; `DEFINES` for file/symbol.
- Absolute and relative local imports, aliases, packages, `__init__.py`, external/unresolved imports and cycles.
- Unique, unshadowed same-module bare-name calls and uniquely resolved imported aliases.
- Attribute calls, including `self`/`cls`, dynamic dispatch, shadowed names, ambiguous targets and unsupported forms remain unresolved or ambiguous and emit no `CALLS` edge.

**Acceptance**
- Every emitted edge has extant endpoints and an exact source span where applicable.
- The only resolved calls are supported static cases: bare-name calls with one unshadowed in-repository binding, or explicitly imported aliases resolving uniquely. Extracting a call site is deterministic; resolving its target is deterministic only within this conservative subset. Attribute calls (including `self`/`cls`), dynamic dispatch, shadowed names, reflection and unsupported forms are unresolved; multiple possible targets are ambiguous. Neither unresolved nor ambiguous calls emit a `CALLS` edge.
- Edge ordering and identity are deterministic.

### Task 11.5 — Graph validation

**Files**
- Add `backend/app/code_graph/validation.py`
- Add `backend/tests/code_graph/test_validation.py`

**Interfaces**
- `GraphValidator.validate(graph: CodeGraph) -> GraphValidationResult`
- Validation rules for unique IDs, known edge endpoints/types, repository consistency, file references, spans, source-hash provenance and sorted/canonical data.

**Tests**
- Inject duplicate IDs, missing endpoints, wrong repository IDs, unknown file/symbol references, negative/reversed/out-of-bounds spans, inconsistent hashes and malformed edge types.
- Structural edges are validated against their edge-type-specific provenance: repository-to-file containment has discovered path/file hash; lexical containment and definitions have child declaration span/hash; imports and calls have statement span/hash.
- Verify diagnostics name the exact entity and failed rule.

**Acceptance**
- Valid fixture graph has zero validation errors.
- Each injected invalid condition fails deterministically with a targeted error.
- This validator is implemented and independently tested before the builder depends on it.

### Task 11.6 — Graph builder

**Files**
- Add `backend/app/code_graph/builder.py`
- Add `backend/tests/code_graph/test_builder.py`
- Update `backend/app/code_graph/__init__.py` exports as needed

**Interfaces**
- `CodeGraphBuilder(root_path, repository_id=None, scanner=None)`
- `build() -> GraphBuildResult`
- Build sequence: discover -> extract -> resolve relationships -> assemble graph -> call `GraphValidator` -> return graph, status and diagnostics.

**Tests**
- Empty repository, normal fixture, syntax error, unreadable file, mixed supported/unsupported files, deterministic input order, partial failure and counts consistency.
- Verify stable IDs and source digests are consistent across nodes and edges.
- Assert status: complete for exhaustive Python-scope success; partial for any syntax error, unreadable in-scope file, or scan truncation while retaining a valid graph; failed for invalid/missing root, fatal scan failure, or validator errors and carries no graph. Unsupported-language files remain listed in coverage and are not represented as semantically analyzed. Expected unresolved/ambiguous relationship diagnostics alone do not make a build partial.

**Acceptance**
- All failure states are surfaced in `GraphBuildResult`; incomplete scans cannot be marked complete.
- A validator error produces `failed` status and cannot yield a valid graph result.
- Build does not start services, call Ollama, write to the repository, or persist to a database.
- Graph assembly is independent of the existing LangGraph workflow.

### Task 11.7 — JSON serialization

**Files**
- Add `backend/app/code_graph/serialization.py`
- Add `backend/tests/code_graph/test_serialization.py`

**Interfaces**
- `serialize_graph(graph: CodeGraph) -> str`
- `deserialize_graph(payload: str) -> CodeGraph`
- Canonical sort keys and explicit schema-version handling.

**Tests**
- Byte-identical JSON from repeated builds and reordered input lists.
- Round trip preserves graph models, IDs, enums, hashes, paths and source spans.
- Unknown schema version and malformed payload return explicit errors.

**Acceptance**
- Same graph snapshot produces identical UTF-8 JSON bytes.
- Serialization contains no absolute machine path in stable IDs.
- Output ordering is defined and covered by tests.

### Task 11.8 — NetworkX runtime and traversal

**Files**
- Add `backend/app/code_graph/graph_runtime.py`
- Add `backend/app/code_graph/queries.py`
- Add `backend/tests/code_graph/test_queries.py`
- Update `backend/pyproject.toml` with a supported NetworkX runtime dependency only if required for the selected implementation; update any tracked lockfile if one exists.

**Interfaces**
- `to_networkx(graph: CodeGraph) -> nx.MultiDiGraph`
- `find_symbols(graph, name_or_qualified_name)`
- `callers(graph, symbol_id, depth=1)`
- `callees(graph, symbol_id, depth=1)`
- `imports(graph, file_id, depth=1)`
- `dependents(graph, file_id, depth=1)`

**Tests**
- Exact and partial symbol search, parallel edge preservation, directionality, cycle termination, bounded depth, deterministic ordering, unknown IDs, and returned edge provenance.
- Graph queries operate on the validated source model and do not add inferred edges.
- Verify import/use of runtime fails explicitly if dependency is unavailable; do not silently fall back to a success-shaped partial graph.

**Acceptance**
- Traversal respects the caller-supplied maximum depth and visits each node at most once per query.
- Returned relationships include their source path/span and resolution confidence.
- NetworkX is only a projection/runtime dependency; canonical serialization remains `CodeGraph`.

### Task 11.9 — Tests and sample repository evaluation

**Files**
- Complete `backend/tests/code_graph/` and `backend/tests/fixtures/code_graph/sample_project/`
- Add a test/evaluation note in test docstrings or fixtures; do not add a separate planning document.
- Do not change existing source modules except for narrowly scoped compatibility adapters approved after the graph tests pass.

**Interfaces**
- One end-to-end fixture test for `CodeGraphBuilder.build()`, validation, canonical serialization and traversal.
- A labeled query fixture for symbol/caller/callee/import lookups.
- An opt-in performance test or benchmark helper, excluded from default fast unit tests if timing is unstable.

**Tests**
- Required scenario matrix from Section 3.
- Existing regression selectors: `test_context_engine.py`, `test_phase4_code_intelligence.py`, `test_phase6_evidence_evaluation.py`, `test_verification_engine.py`, `test_phase8_1_chunking.py` through `test_phase8_6_rag.py`, `test_phase2_tools.py`, and MCP/review integration tests.

**Acceptance**
- Targeted Code Graph tests pass, followed by the relevant regression tests.
- Graph serialization is deterministic and all accepted edges validate against the provenance rules for their edge types.
- A benchmark report records scan/build/validate time for a generated fixture of 1,000 Python files and up to 20,000 symbols, along with hardware, Python version, fixture generation and results. The 10-second target is an optimization goal, not a Phase 11 correctness gate.
- Smart Context recall@5 is not evaluated in Phase 11; it belongs to the future Smart Context integration phase.

## 3. Required test fixture matrix

| Fixture case | Expected behavior |
|---|---|
| Nested classes and functions | Parent/child containment, qualified names and exact spans for each declaration. |
| Absolute/relative local imports | `IMPORTS` edge only when resolution is unique; preserve import statement path/line. |
| External, missing and ambiguous imports | No dangling edge; diagnostic includes target and source span. |
| Direct and imported calls | `CALLS` only for bare-name, unshadowed unique static bindings or explicitly imported aliases resolved uniquely; candidate location is exact. |
| Attribute, dynamic and ambiguous calls | No `CALLS` edge; unresolved/ambiguous diagnostic explains the resolver limitation. This includes `self`/`cls` calls in the initial MVP. |
| Duplicate symbol names | Unique deterministic IDs and independent lookup results. |
| Missing/unreadable/syntax-invalid source | Syntax errors and unreadable in-scope files yield a usable `partial` graph with diagnostics; missing/invalid root or fatal scan/validation failure yields `failed`; never silently claim complete. |
| Cycles | Validation succeeds where edges are valid; traversal terminates and obeys depth bounds. |
| Source edit after build | Rebuilding after a source edit changes the affected file hash and graph source digest; an older graph snapshot is not silently presented as current. |
| Reordered file enumeration | Identical canonical IDs, edge order and serialized JSON. |
| Large generated sample | Document an initial benchmark for 1,000 Python files / up to 20,000 symbols, excluding setup; record environment and results. Ten seconds is an optimization target, not a correctness gate. |

## 4. Implementation and integration gates

1. **Model gate:** Task 11.1 contracts accepted; no NetworkX/DB coupling in models.
2. **Discovery/extraction gate:** Tasks 11.2–11.4 pass deterministic fixture tests and have explicit unresolved behavior.
3. **Validation gate:** Task 11.5 is implemented and tested before any builder relies on it.
4. **Build/integrity gate:** Task 11.6 uses the completed validator; Tasks 11.7–11.8 pass byte-stable serialization and bounded traversal tests; dependency declaration is intentional and reproducible.
5. **Regression gate:** Task 11.9 runs targeted existing tests; preserve public `ProjectMap`, symbol search, verification and MCP behavior.
6. **Scope gate:** Only after Phase 11 acceptance should separate work integrate graph candidates into Smart Context and graph/source provenance into Evidence Engine.

## 5. Follow-on work, not part of Phase 11

- Adapt `ASTCodeAnalyzer`, `ImportAnalyzer`, `SymbolIndex`, `CodeIntelligenceEngine`, and `ProjectMapBuilder` to consume graph output while maintaining compatibility.
- Integrate graph-guided candidates into `HybridRetriever`/`ContextRanker` and wire query embeddings into the RAG path.
- Add `ContextCandidate` and `RetrievedContext`, token estimation, and labeled retrieval evaluation, including the recall@5 >= 0.80 target.
- Add atomic claim, `GraphEvidence`, `SourceEvidence`, and `VerificationResult` adapters across existing verification/review model families.
- Add agent/MCP read-only graph/context/evidence tools through the existing permission-aware `ToolRegistry`.
- Consider a frontend graph/context/evidence UI only after API contracts stabilize.

These are not prerequisites for claiming the Phase 11 graph foundation complete. They are required before claiming the three product pillars are integrated end-to-end.
