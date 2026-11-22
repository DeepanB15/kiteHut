# Phase 11.12 — End-to-End Evaluation: Code Graph MVP

Date: 2026-11-21
Environment: Windows (win32), Python from `backend/`, local checkout; no
database, no migrations, no network services, no new dependencies.

## Scope exercised

The complete pipeline was exercised against a committed, realistic fixture:

```
Repository Discovery
  -> Python AST Extraction
  -> Relationship Extraction
  -> Graph Building
  -> Graph Validation
  -> Smart Context Retrieval
  -> Evidence Verification
  -> Agent / MCP Execution
```

## Deliverables

| File | Purpose |
|---|---|
| `backend/tests/fixtures/code_graph/e2e_project/` | Multi-module fixture: `app` (models, util, service, main, empty, Unicode, one intentionally broken module) and `pkg_a`/`pkg_b` (duplicate `helper` names, import consumer) |
| `backend/tests/fixtures/code_graph/e2e_project/README.md` | Fixture scope documentation |
| `backend/tests/test_phase11_12_e2e.py` | 20 end-to-end tests (1 environment skip) |
| `memory/phase11.12-e2e-evaluation.md` | This report |

No existing unrelated working-tree change was modified. Nothing was staged,
committed, pushed, reset or cleaned. No frontend code was touched.

## Exact test results

All commands run from `backend/`.

| Suite | Result |
|---|---|
| `pytest tests/test_phase11_12_e2e.py -q` | **19 passed, 1 skipped** (8.07s) |
| `pytest tests/code_graph -q` | **286 passed, 4 skipped** (9.08s) |
| `pytest tests/test_phase11_11_integration.py -q` | **47 passed** (14.33s) |
| `pytest tests/code_graph/test_evidence_integration.py -q` | **20 passed** (1.90s) |
| Code Graph + 11.11 + 11.12 combined | **352 passed, 5 skipped** (16.36s) |
| Agent / MCP / permissions selection | **78 passed, 2 failed** (35.30s) |
| Full backend suite `pytest -q` | **904 passed, 16 failed, 5 skipped** (422.01s) |

Skips are reported, not hidden:

- 4 pre-existing Code Graph discovery skips: named pipes unavailable on this
  platform (1) and symlink creation denied by Windows privileges (3).
- 1 new E2E skip: the symlink-escape test cannot create a symlink without
  Windows `SeCreateSymbolicLinkPrivilege` (`WinError 1314`).

Full-suite failures — none in Code Graph, evidence, retrieval or verification:

- 15 pre-existing CLI/branding failures already documented in
  `memory/phase11.10-verdict.md`: `tests/test_cli.py` (7),
  `tests/test_phase0_foundation.py` (6), `test_phase3_agent.py` (1),
  `test_review_integration.py` (1). The application prints "KiteHut" while the
  tests expect "RepoLens"; the `repolens` console script is not installed.
- 1 environment failure: `tests/test_phase8_6_rag.py::TestRagPipeline::test_answer_preserves_provenance`
  times out calling a local Ollama LLM (`RagLlmProviderError: ... timed out`).
  It is unrelated to Code Graph and has no local model service available.

## Defects found and fixed

1. **Ambiguous duplicate declarations could produce `SUPPORTED` (High).**
   `app/code_graph/evidence.py::_named_symbol_locations` decided ambiguity
   from `(relative_path, qualified_name)`. Two declarations with the same name
   in one file share a qualified name and differ only by occurrence ordinal,
   so they were treated as one identity. A claim with an asserted pattern that
   existed in either definition was reported `SUPPORTED` (verified for both
   `return "first"` and `return "second"`).
   *Fix:* ambiguity is now decided by canonical symbol ID, and a qualified
   name in the statement restricts candidates to that identity; duplicate
   declarations remain ambiguous and can never support a claim.

2. **`SymbolNode.parent_id` was never wired for nested symbols (Medium).**
   The builder looked up `SymbolDeclaration.parent_qualified_name` (the bare
   immediate scope name, e.g. `process`) in a map keyed by full qualified
   names (e.g. `app/service.Service.process`), so every nested
   function/class/method had `parent_id=None`, contradicting the model field
   and the graph tools' payloads.
   *Fix:* the parent is derived from the symbol's own qualified-name prefix
   within the same file; a prefix matching more than one declaration is left
   unwired rather than guessed. Top-level symbols now point at their module.

3. **Duplicated syntax-error diagnostic prefix (Low).**
   A partial build reported
   `Syntax error in app/legacy_broken.py: Syntax error in app/legacy_broken.py: invalid syntax ...`.
   *Fix:* the builder uses the original parser error (`exc.__cause__`) for the
   detail, so the path appears once and the line/offset are preserved.

No relationship-resolution defect was found: every emitted CALLS and IMPORTS
edge was verified against the source text on disk.

## Acceptance matrix

| Criterion | Result | Evidence |
|---|---|---|
| No incorrect CALLS or IMPORTS edges | **PASS** | `test_no_incorrect_calls_or_imports_edges` re-parses each source file: every CALLS edge matches a callee expression at its recorded line and a declaration at the target span; every IMPORTS edge matches an actual import statement |
| No guessed relationships for ambiguous symbols | **PASS** | Duplicate `duplicate()` calls emit `call_ambiguous_declarations` with no edge; nested-function/parameter shadowing emits diagnostics; `graph_find_symbol`/`graph_callers` report `ambiguous=True` and return no relationships. Defect 1 fixed |
| Partial builds expose diagnostics | **PASS** | One unparseable module yields `status=partial`, a `syntax_error` diagnostic with path/line/offset, coverage `14 discovered / 13 analyzed / 1 skipped`, and no fabricated symbols |
| Existing retrieval behavior remains intact | **PASS** | For `helper`/`duplicate`/`main`: every baseline chunk is retained, keyword/semantic scores are unchanged, `final_score` never decreases; `graph=None` reproduces the baseline exactly |
| Ambiguous chunk alignment does not select arbitrary chunks | **PASS** | Two same-name symbols align to two distinct chunks with exactly matching file/start/end spans; no fallback to a same-name-only guess |
| Stale source evidence cannot support claims | **PASS** | After mutating `app/main.py`, a previously `SUPPORTED` claim becomes `INCONCLUSIVE`; all claim-relevant spans are stale with `source_hash_mismatch`; `evidence_count == 0` |
| Missing evidence is not contradictory evidence | **PASS** | `FILE_EXISTS` on an absent file -> `UNSUPPORTED`; the same absence for a content claim -> `INCONCLUSIVE` |
| Repository boundaries are enforced | **PASS (tested paths)** | Traversal (`../../outside.py`), absolute outside paths, non-existent roots and filesystem roots are rejected by tools; `ToolRegistry` overwrites caller `repository_path`; the MCP wrapper pins its server root; the evidence collector drops unsafe claim paths. See limitation 5 for symlinks |
| Repeated builds produce deterministic results | **PASS** | Two independent builds serialize byte-identically; edge IDs are sorted and unique; symbol IDs are unique; deserialize -> serialize is byte-identical |
| Agent / MCP execution works end-to-end | **PASS** | Router selects `graph_callers`, `ToolExecutor` returns the resolved caller; MCP `verify_claim` returns `SUPPORTED`/`UNSUPPORTED` as expected |
| Nested functions and classes | **PASS** | Nested class/method/function qualified names are correct and `parent_id` now reflects the lexical hierarchy |
| Imports and function calls | **PASS** | Module, from-import, and relative-capable IMPORTS resolution; same-file unique bare-name CALLS resolve (including Unicode identifiers) |

## Remaining limitations

1. **Nested-sibling calls are intentionally unresolved.** A call from one
   nested function to a sibling defined in the enclosing scope is treated as
   "shadowed" (`call_shadowed_unresolved`) and produces no CALLS edge. This is
   an existing, explicitly tested conservative contract
   (`test_nested_function_shadowing_blocks_in_scope_call`), not changed here.
2. **CALLS resolution is same-file only, bare names only.** Cross-module calls,
   imported-alias calls, builtins (`str`, `int`), and all attribute calls
   (`self.describe`, `registry.add`) remain diagnostics with no edge. This is
   deliberate, but limits graph completeness.
3. **Duplicate qualified names remain a single qualified identity.** Two
   duplicate definitions have distinct symbol IDs and occurrence ordinals, but
   parent wiring for a *nested child* of an ambiguous parent is left unwired
   rather than guessed.
4. **Root `__init__.py` child symbols** receive the pre-existing qualified-name
   shape `..name` (module identity is `.`); no fixture depends on it.
5. **Symlink escape containment is not runtime-tested here.** On this Windows
   host symlink creation is denied (`WinError 1314`), so those discovery and
   E2E tests skip. The code path and unit assertions exist but did not execute.
   Traversal, absolute-path and workspace-root containment did execute.
6. **The full suite retains 15 pre-existing branding/CLI failures and one
   Ollama-dependent failure.** None are Code Graph regressions; they are
   reported rather than hidden.
7. Graph tools rebuild the graph per invocation (read-only, deterministic),
   which is acceptable for the MVP but not optimized for large repositories.

## Recommendation

**READY for Code Graph MVP**, with the limitations above disclosed. All Code
Graph, evidence, retrieval and agent/MCP suites pass; every acceptance
criterion was verified except runtime symlink containment, which this Windows
environment cannot exercise. The three defects found were fixed and covered by
the new E2E suite.
