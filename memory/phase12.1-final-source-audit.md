# Phase 12.1 — Final Source-Level Audit

**Date:** 2026-11-21
**Scope:** KiteHut Code Graph MVP, Phase 11 source changes (11.9–11.12) and the
Phase 12.1 release gate.
**Mode:** Audit first, then repair only confirmed release-blocking defects.

**Repository state during audit:** dirty working tree with pre-existing,
unrelated security-hardening edits. `app/code_graph/evidence.py`,
`app/code_graph/integration.py`, `app/tools/code_graph_tools.py`, the Phase
11.11/11.12 tests and the new fixtures are **untracked**. Nothing was staged,
committed, pushed, reset, cleaned, tagged, or discarded.

---

## 1. Files reviewed

### Source

| File | What was checked |
|---|---|
| `backend/app/code_graph/builder.py` | Pipeline, statuses, diagnostics, Phase 11.12 parent/syntax fixes, edge assembly/dedupe |
| `backend/app/code_graph/evidence.py` (untracked) | Evidence planning, ambiguity gate, freshness, containment, three-status projection, new entry point |
| `backend/app/code_graph/integration.py` (untracked) | Graph candidates, merge with hybrid retrieval, score/relationship semantics |
| `backend/app/code_graph/discovery.py` | File walking, symlink rejection, ignore rules, encoding/read failures, limits |
| `backend/app/code_graph/python_extractor.py` | Symbol extraction, spans, decorators, nested declarations, imports/calls |
| `backend/app/code_graph/relationships.py` | Import/call resolution, ambiguity handling, `diagnostics` population |
| `backend/app/code_graph/validation.py` | All eight validation families and their failure paths |
| `backend/app/code_graph/serialization.py` | Canonical JSON, schema gate, atomic write |
| `backend/app/code_graph/queries.py` | Deterministic BFS, depth/result bounds, cycle handling |
| `backend/app/code_graph/models.py` | IDs, path normalization, hash/span contracts, schema constants |
| `backend/app/core/path_guard.py` | `resolve_repository_path` rejection rules and symlink resolution |
| `backend/app/chunking/repository_chunker.py` | `chunk_repo` traversal and path handling |
| `backend/app/verification/verification_engine.py` | Claim entry point, verdict selection, collector construction |
| `backend/app/verification/collectors/evidence_collector.py` | Pre-existing collector path joining/reads (root cause review) |
| `backend/app/tools/base.py` | Exception-to-`ToolResult` boundary |
| `backend/app/tools/code_graph_tools.py` (untracked) | Six graph/verification tools, argument validation, payload shaping |
| `backend/app/tools/registry.py` | Registration, lookup, permission/risk metadata |
| `backend/app/mcp/server.py` | MCP wrappers and tool exposure |
| `backend/app/agent/router/router.py` | Graph intent routing and prompt/context use |
| `backend/app/agent/router/tool_executor.py` | Tool dispatch, result propagation |
| `backend/app/agent/router/tool_router_contracts.py` | Route contracts and validation |

### Tests and fixtures

| Path | What was checked |
|---|---|
| `backend/tests/code_graph/test_evidence_integration.py` | Evidence statuses, stale/ambiguous/missing cases, graph fallback, provenance |
| `backend/tests/test_phase11_11_integration.py` | Tools, context integration, routing, MCP, permissions |
| `backend/tests/test_phase11_12_e2e.py` | 20 end-to-end tests across build → tools → evidence → MCP |
| `backend/tests/fixtures/code_graph/sample_project/**` | Fixture semantics used by the E2E assertions |
| `backend/tests/test_phase9_2_router.py` | Router regression surface |
| `backend/tests/test_review_integration.py` | Review path regression surface |
| `backend/tests/test_import_regressions.py` | Determinism assertions (one vacuous assertion found) |
| `memory/phase11.9-*`, `memory/phase11.10-*`, `memory/phase11.12-e2e-evaluation.md` | Stated contracts and prior evidence |

No database was started, no migration was run, no service was contacted, and no
frontend file was modified.

---

## 2. Phase 11.12 corrections — verification result

All three prior corrections are **correct and complete**. They were verified by
source inspection and by direct execution against temporary repositories, not
only by the existing tests.

### A. Duplicate qualified names remain ambiguous — PASS

- `evidence.py` builds canonical symbol IDs from the qualified name plus an
  ordinal, and classifies a claim pattern as ambiguous whenever more than one
  declaration carries the same symbol identity/name.
- Probes with two same-qualified-name declarations returning `"first"` and
  `"second"` produced, for **both** exact patterns:
  `status=INCONCLUSIVE`, `evidence_items == []`, and spans labeled
  `ambiguous=True`.
- An exact pattern does **not** bypass ambiguity; no arbitrary first-match
  evidence is produced.
- The behavior is conservative in the intended direction: ambiguity suppresses
  support rather than inventing a winner.

### B. Nested `parent_id` linkage — PASS

- Parent selection uses the qualified-name prefix chain rather than bare text
  matching.
- Verified `pkg/mod.Outer.Inner.m.n`: `outer`, `Inner`, `m`, `n` all have the
  correct immediate parent.
- For duplicate qualified parents, children keep `parent_id = None` rather than
  attaching to an arbitrary declaration.
- Every non-null parent exists in the same file, encloses the child span, and
  `validate_graph()` reports the graph valid.

### C. Syntax-error diagnostics — PASS

- Extraction failures are reported once, with the file path appearing once and
  no duplicated `Syntax error in ...` prefix.
- Observed: `Syntax error in broken.py: invalid syntax (line 1, offset 12)`.
- Null-byte input reports `... cannot contain null bytes` with `line=None` and
  does not crash the build; the result is `PARTIAL` and the remaining graph is
  usable.

No defect was found in any of the three corrections.

---

## 3. Confirmed defects

| ID | Defect | Severity | Status |
|---|---|---|---|
| F1 | `verify_claim_with_graph` delegated to the pre-existing collector, which read `root / target_file` without containment; `..`/absolute targets could read outside the repository | **High (release-blocking)** | **Fixed in this audit** |
| F2 | `builder.py` discards `relationship.diagnostics`; error-severity relationship diagnostics can be lost even when the build reports `COMPLETE` | Medium | Open, non-blocking |
| F3 | `validate_graph` does not reject a symbol/file with multiple `CONTAINS` parents (check omitted although the docstring claims structural completeness) | Low | Open, non-blocking |
| F4 | `chunk_repo` uses `rglob("*.py")` without rejecting symlinked files, so a file symlink can cause an outside file to be read/chunked; output used by `graph_context` is metadata-only | Low | Open, non-blocking |
| F5 | One vacuous and several redundant/over-broad test assertions create false confidence (details in §6) | Low | Open, non-blocking |
| F6 | `graph_context` can append graph candidates whose files were excluded by the `max_files` chunk bound, producing metadata-only candidates without chunk content | Low | Open, non-blocking |

### F1 — containment escape (fixed)

**Location:** `backend/app/code_graph/evidence.py`,
`verify_claim_with_graph()`.

**Cause:** the graph layer correctly normalized/dropped unsafe claim paths, but
then called `verification_engine.collector.collect_for_claim(claim)`. The
pre-existing Phase 7 collector joins `self.root_path / claim.target_file` and
reads it, with no containment check.

**Observed before the fix:** a claim with
`target_file="../outside_secret.py"` (and separately an absolute path) produced
evidence from the outside file, including source content, and could reach
`SUPPORTED`. This was reachable through the public verification entry point,
not only through a hand-built `ExtractedClaim`.

**Fix:**

- Added `_claim_target_contained()` in `evidence.py`. It uses the shared
  `resolve_repository_path()` guard, which rejects empty paths, absolute paths
  (POSIX, drive-letter, UNC), any `..` component, and symlink escapes.
- `verify_claim_with_graph` now records
  `diagnostics["claim_target_within_repository"]` and invokes the existing
  collector **only** when the target is contained. A claim without a target
  file is contained by definition.
- No change was made to the pre-existing Phase 7 collector or to unrelated
  verification behavior.

**Verified after the fix:** both traversal and absolute targets yield
`status=INCONCLUSIVE`, `verdict=UNCERTAIN`, `evidence_ids == []`,
`claim_target_within_repository=False`, and no evidence item whose
`source_file` ends in `outside.py`.

**Regression coverage:** `tests/test_phase11_12_e2e.py::
test_repository_boundaries_are_enforced` now exercises the public
`verify_claim_with_graph` entry point directly for both unsafe forms, in
addition to the existing tool-layer assertions.

### F2 — dropped relationship diagnostics

`builder.build()` consumes `relationship.edges`, `unresolved_imports` and
`unresolved_calls`, but never merges `relationship.diagnostics` into
`GraphBuildResult.errors/warnings`. A failure such as
`edge_creation_error`, `call_site_validation_error` or an extraction warning is
therefore invisible unless it independently downgrades the build. The builder's
own docstring says unresolved/ambiguous relationships must not downgrade a
build, and the graph remains usable; the defect is diagnostic completeness, not
silent corruption. It can hide a missing edge. Not release-blocking for the MVP,
but should be fixed before diagnostic output is treated as authoritative.

### F3 — multiple `CONTAINS` parents accepted

`validate_structural_consistency` records one parent per child and does not
reject a second `CONTAINS` edge. The builder emits one structural parent by
construction, so this is defense-in-depth for deserialized/hand-built graphs.
No current path produces it.

### F4 — `chunk_repo` symlink traversal

`repository_chunker.chunk_repo` enumerates `repo.rglob("*.py")` and filters
hidden/cache directories, but does not check `is_symlink()` or confine resolved
paths. A file symlink inside the repository pointing outside will be read and
chunked. `graph_context` only returns chunk metadata (ids, paths, symbols,
spans), not content, and the code graph scanner itself rejects symlinks, so the
leak surface is limited; the read still occurs. Low severity, pre-existing, and
not introduced by Phase 11.12.

### F5 — test assertion quality

See §6.

### F6 — candidate/chunk-set mismatch

`graph_context` bounds chunking with `max_files` but integrates graph candidates
from the whole graph. A graph candidate in a file beyond the chunk bound is
appended without a backing chunk, so downstream context assembly may see a
candidate it cannot hydrate. Deterministic and non-crashing, but worth aligning
the bounds or marking such candidates.

---

## 4. Test results (exact)

All results below are from the post-fix working tree. The full suite was run
**after** the F1 fix and the boundary-test extension.

### Full backend suite

```
cd backend && python -m pytest -q
16 failed, 904 passed, 5 skipped, 65 warnings in 492.37s (0:08:12)
```

The 16 failures are the same pre-existing failures recorded before this audit;
none is in the Code Graph, evidence, integration, router, MCP or permissions
areas:

```
tests/test_cli.py::TestCliCommands::{test_init_command, test_status_command,
  test_doctor_command, test_review_command, test_report_command_markdown,
  test_report_command_save_file, test_ask_command}
tests/test_phase0_foundation.py::{test_pyproject_exists_and_declares_project,
  test_pyproject_declares_console_entry_point, test_console_script_is_installed,
  test_console_script_help_output, test_console_script_version,
  test_click_cli_init_runs_end_to_end}
tests/test_phase3_agent.py::test_cli_init_runs_on_temp_workspace
tests/test_review_integration.py::TestReviewIntegration::test_review_command_still_works
tests/test_phase8_6_rag.py::TestRagPipeline::test_answer_preserves_provenance
```

15 are the known KiteHut-vs-RepoLens CLI/branding and console-entry-point
failures (previously reproduced against a clean `git archive HEAD`); the
remaining one is the known Ollama-timeout test. There are **no new failures**
and no changed pass/skip counts relative to the pre-audit baseline.

### Targeted Code Graph / router / E2E suite

```
cd backend && python -m pytest tests/code_graph tests/test_phase9_2_router.py \
  tests/test_phase11_11_integration.py tests/test_phase11_12_e2e.py -q
377 passed, 5 skipped in 13.58s
```

Breakdown from the post-fix runs:

| Suite | Result |
|---|---|
| `tests/code_graph` | **286 passed, 4 skipped** |
| `tests/test_phase11_11_integration.py` + `tests/test_phase11_12_e2e.py` | **66 passed, 1 skipped** |
| `tests/test_phase11_12_e2e.py` alone (20 tests) | **19 passed, 1 skipped** (symlink test) |

The 5 skips are all environment-gated symlink tests (`WinError 1314`, privilege
not held on this Windows host), not failures and not silently swallowed
assertions.

### Selected agent / MCP / permissions run

The agent/router/MCP/permissions selection used during the audit reported
**78 passed, 2 failed**; both failures are CLI branding cases already in the
16 above (`test_phase3_agent.py::test_cli_init_runs_on_temp_workspace` and
`test_review_integration.py::TestReviewIntegration::test_review_command_still_works`).
All router, tool-registry, MCP-wrapper and permission tests passed.

### Not covered by execution

- POSIX symlink-escape execution (skipped on this host); logic inspected.
- Ollama-backed end-to-end answer generation (the one known timeout above).
- Performance/scale measurements.
- Frontend/UI (out of scope).
- Database startup/migrations (explicitly excluded).

---

## 5. Security findings

1. **Fixed — repository containment on the verification path (High).** See F1.
   The graph evidence layer and the tool layer both rejected unsafe paths; the
   gap was the delegation to the pre-existing collector. The entry point now
   gates that call, records a diagnostic, and emits no outside evidence.
2. **Residual, pre-existing — the Phase 7 collector itself is still unsafe for
   other callers (High if untrusted targets reach it).**
   `EvidenceCollector.collect_for_claim` still performs
   `root_path / claim.target_file` without containment, and
   `VerificationEngine.verify_finding` reaches it through
   `collect_evidence_for_claims`. The Code Graph path is now guarded, but any
   other path that supplies model-derived `target_file` values inherits the
   traversal/absolute-path read. This audit did not modify that pre-existing
   subsystem (out of scope); it should receive the same containment guard
   before verification is exposed to untrusted claims.
3. **Read-only surface.** The six graph/verification tools perform reads,
   in-memory assembly and JSON serialization only: no shell execution, no file
   writes, no network calls, no database access.
4. **Tool-layer path validation.** `graph_files`, `graph_symbols`,
   `graph_imports`, `graph_relationships` and `graph_context` reject traversal
   and absolute paths through the shared guard; registry-level tests confirm the
   errors surface as failed `ToolResult`s.
5. **Symlinks.** Code graph discovery rejects symlinked files and directories
   (including Windows junction detection). The separate chunker caveat is F4.
6. **No source leakage in `graph_context`.** Graph candidates and chunks are
   reduced to ids, paths, symbols, spans and scores; file content is not placed
   in the tool payload.
7. **Permissions/MCP.** Graph tools are registered read-only/low-risk and are
   reachable through MCP with the same argument validation as the registry
   path; no privilege escalation or auto-approval change was found.

---

## 6. Weak, redundant or vacuous assertions

These do not fail and are not release-blocking, but they should not be counted
as independent evidence of correctness.

1. **Vacuous — `backend/tests/test_import_regressions.py:455`:**
   `ids1 == sorted(ids1) or ids1 == ids1`. The second disjunct is always true,
   so the determinism/order assertion can never fail. It should be reduced to
   the first comparison (or removed if covered elsewhere).
2. **Redundant — `backend/tests/test_phase11_11_integration.py:458`:** asserts
   a condition already guaranteed by the preceding assertion; it adds no
   coverage.
3. **Over-broad — `backend/tests/test_phase11_11_integration.py:687`:** an
   `or`-joined condition allows one branch to satisfy the assertion while the
   other regresses. Split it into separate assertions.
4. **Potentially vacuous `all(...)` checks — evidence integration tests:**
   several `all(...)` assertions would pass on an empty collection. In the
   current tests they are paired with non-empty/status assertions, so they do
   not currently mask a failure, but the pattern is fragile; assert
   non-emptiness first where it matters.

No test was changed or weakened to make the audit pass. The only test edit was
the **addition** of direct-API escape assertions for F1.

---

## 7. Remaining limitations

1. **Graph relationships are navigation only.** They are never proof of runtime
   behavior; `SUPPORTED` requires fresh, unambiguous, claim-relevant source
   evidence.
2. **Absential claims** (`CONFIG_KEY_MISSING`, `UNTESTED_MODULE`, etc.) remain
   `INCONCLUSIVE` even when the existing verifier returns `TRUE`, because the
   graph layer has no positive pattern to corroborate. This is deliberate but
   stricter than the pre-existing engine.
3. **File-level pattern matching.** Without `target_line`, a pattern may match
   anywhere in the file or symbol span; it proves text presence, not semantics.
4. **`expected_pattern` is the only asserted-snippet field.** Claims carrying
   only `code_snippet` cannot reach `SUPPORTED`; claim extraction was not
   changed.
5. **Relationship diagnostics are dropped (F2),** so some unresolved/ambiguous
   relationship details never reach the build result even though the graph
   remains usable.
6. **Validation does not enforce single-parent `CONTAINS` (F3)** for
   deserialized/hand-built graphs.
7. **`chunk_repo` follows file symlinks (F4).** Metadata-only tool output limits
   exposure, but the read occurs.
8. **Symlink containment is not exercised at runtime on this Windows host**
   (`WinError 1314`); the POSIX path was verified by inspection and the
   non-symlink traversal/absolute cases were executed.
9. **No performance or scale evidence.** BFS bounds and `max_files` exist, but
   no large-repository benchmark was run in this audit.
10. **Full-suite green is not claimed.** 16 pre-existing failures remain
    (15 branding/entry-point, 1 Ollama timeout); they are environmental or
    product-branding issues, not Code Graph regressions.

---

## 8. Acceptance matrix

| Area / check | Result | Evidence |
|---|---|---|
| Phase 11.12-A duplicate-name ambiguity | **PASS** | Both exact patterns `INCONCLUSIVE`, no evidence, spans ambiguous |
| Phase 11.12-B nested `parent_id` | **PASS** | Correct chain; ambiguous parents `None`; `validate_graph` valid |
| Phase 11.12-C syntax diagnostics | **PASS** | Single path, line/offset preserved; null-byte handled; `PARTIAL` graph usable |
| Build statuses and partial-graph recovery | **PASS** | Source review + targeted suites; `COMPLETE`/`PARTIAL`/`FAILED` paths exercised |
| Query helpers and deterministic ordering | **PASS** | Code Graph tests (286 passed) |
| Evidence statuses (`SUPPORTED`/`UNSUPPORTED`/`INCONCLUSIVE`) | **PASS** | Evidence integration suite + probes |
| Stale-evidence downgrade and hash checks | **PASS** | Suite covers mismatch/unavailable/span bounds |
| Repository containment on the verification path | **PASS (after F1 fix)** | Public API returns no outside evidence; regression assertions added |
| Graph tools registration and argument validation | **PASS** | Registry/tool tests; traversal/absolute errors surface as failures |
| MCP exposure of graph tools | **PASS** | MCP-wrapper tests in the targeted suites |
| Agent/router integration | **PASS** | Router suite passed; only pre-existing CLI branding failures elsewhere |
| Permissions / risk metadata | **PASS** | Permission tests passed in the selected run |
| Full backend suite green | **FAIL (pre-existing only)** | 904 passed, 16 failed, 5 skipped; failure list identical to baseline |
| Windows symlink-escape runtime | **NOT TESTED** | Skips: `WinError 1314` privilege not held; logic reviewed |
| Ollama-backed end-to-end RAG | **NOT TESTED** | Known timeout test; not required for source audit |
| Performance / large-repository scale | **NOT TESTED** | No benchmark run |
| Frontend / UI | **NOT TESTED (out of scope)** | Not modified |
| Database startup / migrations | **NOT TESTED (excluded)** | Not run by instruction |
| Release tree completeness | **NOT TESTED / AT RISK** | Core Phase 11 files (`evidence.py`, `integration.py`, `code_graph_tools.py`, tests, fixtures) are untracked; HEAD does not contain the audited fix |

---

## 9. Recommendation

**READY — for the audited working tree, conditional on releasing that tree
(including the untracked Phase 11 files and the F1 fix).**

Rationale:

- All three Phase 11.12 corrections are correct.
- The one release-blocking defect found in this audit (F1, outside-repository
  read through the verification entry point) is fixed and regression-tested.
- All Code Graph, evidence, router, MCP and permissions tests pass; the full
  suite has no new failures and only the known 16 pre-existing ones.
- Remaining findings F2–F6 are non-blocking diagnostic/validation/test-quality
  issues and are documented above.

**Conditions before cutting a release:**

1. **Include the audited tree in the release.** A build from `git HEAD` alone
   would omit `evidence.py`, `integration.py`, `code_graph_tools.py`, the new
   tests/fixtures and therefore the F1 fix. This is a packaging blocker, not a
   source blocker.
2. **Track the residual collector risk (R2).** The pre-existing
   `EvidenceCollector.collect_for_claim` remains path-unsafe for non-Code-Graph
   callers. If the release exposes verification/review to untrusted claims,
   that guard is release-blocking for those surfaces and must be fixed
   separately.
3. **Accept or schedule F2–F6**; none changes a release decision, but F2 should
   be fixed before relationship diagnostics are presented as authoritative.

**Verdict: READY for release preparation of the audited working tree. NOT READY
to release from `HEAD` as-is, because the audited Code Graph files are
untracked.**
