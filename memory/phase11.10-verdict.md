# Phase 11.10 — Evidence Engine Integration: VERDICT

## APPROVED

### Deliverable summary

Code Graph evidence discovery is connected to the existing verification
subsystem through a single adapter module. Existing claim, evidence, collector
and verifier components are reused unchanged; the only addition to the engine
is an eight-line claim-level entry point. Final statuses are exactly
`SUPPORTED` / `UNSUPPORTED` / `INCONCLUSIVE`, and graph relationships are only
ever navigation evidence.

### Exact files changed

| File | Change |
|---|---|
| `backend/app/code_graph/evidence.py` | New 975-line module: `EvidenceStatus`, `SourceSpanEvidence`, `GraphEvidenceBundle`, `GraphVerificationOutcome`, `collect_graph_evidence()`, `verify_claim_with_graph()`; replaces the unfinished draft that derived support from graph heuristics |
| `backend/app/verification/verification_engine.py` | Additive `VerificationEngine.verify_claim(claim, evidence_items)` (delegates to the existing `_select_verifier`); imports for `ExtractedClaim` / `EvidenceItem`. No existing method changed |
| `backend/tests/code_graph/test_evidence_integration.py` | New 15-test focused suite |
| `memory/phase11.10-integration.md` | Architecture and data flow |
| `memory/phase11.10-verdict.md` | This document |

No dependencies, databases, migrations, startup code, frontend code or
Phase 11.11 work were touched. Nothing was staged, committed or cleaned.

### Tests actually run

Focused suite — `python -m pytest tests/code_graph/test_evidence_integration.py -q`:

```
15 passed
```

Coverage (one or more tests each): supported claim with valid source evidence
(target span and symbol declaration), unsupported claim with contradictory
source evidence (absent target file / non-corroborating structural item),
inconclusive claim with missing evidence, claim with no source locations,
stale source evidence (status downgrade + hash mismatch metadata), ambiguous
graph relationships (duplicate bare symbol, navigation only), graph unavailable
fallback (`graph=None`), invalid schema fallback (`schema_version=99`),
provenance/repository identity preservation, named-symbol identity, navigation
labels, and the existing engine's claim entry point.

Regression — `tests/code_graph tests/test_verification_engine.py
tests/test_phase6_evidence_evaluation.py tests/test_phase7_integration.py
tests/test_phase5_review_engine.py`:

```
306 passed, 4 skipped
```

Full suite — `python -m pytest -q`:

```
834 passed, 15 failed, 4 skipped
```

All 15 failures are pre-existing at HEAD and unrelated to this phase: they are
CLI branding/console-entry-point tests (`test_cli.py`, `test_phase0_foundation.py`,
`test_phase3_agent.py::test_cli_init_runs_on_temp_workspace`,
`test_review_integration.py::test_review_command_still_works`). I reproduced
them against a clean `git archive HEAD` extraction of the repository, where
the same tests fail for the same reasons (output says "KiteHut" while tests
expect "RepoLens"; `repolens` console script not installed). No verification,
review or code-graph test failed.

### Source-level review findings

Strengths / requirement compliance:

1. **No second engine.** Evidence uses `EvidenceItem`; verification uses
   `VerificationEngine.verify_claim`; the verdict comes from the existing
   domain verifiers. No verification rule was duplicated or replaced.
2. **Navigation is not proof.** Caller/callee/import/dependent spans are kept
   in `GraphEvidenceBundle.spans` and diagnostics only. `_select_verification_evidence`
   refuses to forward non-claim-relevant spans, so an edge alone can never
   produce corroborating evidence.
3. **Conservative support gate.** `SUPPORTED` needs a fresh, unambiguous,
   claim-relevant source span that either contains `expected_pattern`
   (whitespace-normalised) or confirms a `FILE_EXISTS` / `AST_SYMBOL_EXISTS`
   claim, *and* that evidence id must be one the existing verifier relied on.
   Stale, ambiguous, missing or purely navigational evidence therefore cannot
   yield `SUPPORTED`.
4. **Freshness.** Staleness uses the graph's own contract: SHA-256 of file
   bytes versus `FileNode.content_hash` / `SymbolNode.source_hash`
   (`source_hash_mismatch`), plus `line_span_outside_file`,
   `line_span_exceeds_file`, `source_file_unavailable`,
   `path_outside_repository`. Stale spans are excluded from verifier input and
   counted in diagnostics.
5. **Provenance and repository identity.** Each span records
   `repository_id`, `file_id`, `symbol_id`, relationship/depth, span content
   hash, whole-file hash and the originating edge provenance. Graph nodes whose
   `repository_id` disagrees with the graph repository are skipped
   (`repository_identity_consistent=False`).
6. **Determinism.** Locations are planned in a fixed order, capped at 8, and
   evidence ids are `graph_ev_<sha256[:16]>`.
7. **Path safety.** Claim paths go through `normalize_repository_path`
   (no absolute paths, no `..`) and reads are guarded with
   `Path.is_relative_to(repository_root)`.
8. **Fallback.** `graph=None` or an invalid schema degrades to direct
   claim-target reads; the focused tests confirm `SUPPORTED` is still possible
   without a graph.

Deliberate limitations recorded for reviewers:

1. **Absential claims stay `INCONCLUSIVE`.** Claims whose truth is "something is
   absent" (`CONFIG_KEY_MISSING`, `UNTESTED_MODULE`) have no positive source
   pattern to verify; even if the existing verifier returns `TRUE`, the gate
   does not promote them. This is the intended reading of requirement 8
   ("insufficient evidence must not be reported as SUPPORTED"), but it is
   stricter than the pre-existing engine.
2. **File-level pattern matching.** If a claim omits `target_line`, the asserted
   pattern is matched anywhere in the target file (or in a graph-located
   symbol span). This proves the literal source text exists, not that its
   runtime behaviour matches the claim (requirement 9).
3. **Module symbols are ignored** for symbol navigation because their spans
   cover the entire file and add no locational precision.
4. **`expected_pattern` is the only asserted-snippet field.** Phase 7 claims
   populated from findings usually carry `code_snippet`; claim extraction is
   unchanged, so claims without an expected pattern can only be `UNSUPPORTED`
   or `INCONCLUSIVE`.
5. Existing Phase 3 (`app/models/*`, `app/services/*`, `app/engines/truth_engine.py`)
   and Phase 5/6 review paths are untouched, so their contracts remain exactly
   as before.

No blocking defects were found. The 15 full-suite failures are environmental /
branding issues already present at HEAD, not regressions from Phase 11.10.

## Verdict: APPROVED for Phase 11.10
