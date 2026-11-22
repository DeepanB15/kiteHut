# Phase 12.2 — Shared Evidence Collector Security Hardening

**Date:** 2026-11-21
**Scope:** Repository path containment at the shared
`EvidenceCollector` boundary (`backend/app/verification/collectors/evidence_collector.py`).
**Result:** PASS — the containment defect is fixed at the shared boundary, all
affected callers were exercised, and no new test failures were introduced.

Nothing was staged, committed, pushed, reset, cleaned or tagged. No new
dependencies, databases, migrations or services were added.

---

## 1. Root cause

`EvidenceCollector` is the shared source-evidence reader used by the
review/verification pipeline and the Code Graph evidence adapter. It built the
read path directly:

```python
full_path = self.root_path / claim.target_file
```

`claim.target_file` is derived from a `Finding.file_path` (which can come from
model output) or supplied directly by an API caller. `pathlib`'s `/` operator
does not enforce containment: `../` components, absolute paths and symlinks are
all resolved normally by the subsequent `.exists()` / `.read_text()` calls.
The collector therefore read and returned evidence from outside the authorized
repository root.

The same file also read `.env.example` with `self.root_path / ".env.example"`
without checking for a symlinked template pointing outside.

Phase 12.1 had added a local pre-check inside the Code Graph verification
entry point, but that protected only that one caller. Direct callers,
`VerificationEngine.verify_finding` / `verify_report`, and any future caller of
`collect_for_claim` remained exposed. The root fix belongs in the shared
collector, not in each caller.

---

## 2. Files changed

| File | Change |
|---|---|
| `backend/app/verification/collectors/evidence_collector.py` | Added shared containment resolution for every claim target and for `.env.example`; rejected paths return no evidence and append structured diagnostics; batch collection resets diagnostics. |
| `backend/app/code_graph/evidence.py` | Comment-only update: the Code Graph pre-check is now documented as defense in depth because the shared collector enforces the same policy itself. |
| `backend/tests/test_evidence_collector_security.py` | New 10-test regression suite: valid, missing, traversal, absolute (external and internal), symlink escape, symlinked `.env.example`, mixed batch, review pipeline, unsafe finding, and Code Graph compatibility. |

No other production file was modified. `VerificationEngine` required no change:
it already routes all evidence collection through the hardened collector.

### Diagnostics contract

Rejected paths are recorded on `collector.path_diagnostics` as structured
dictionaries:

```json
{
  "code": "claim_target_path_rejected",
  "reason": "absolute_path | path_traversal | outside_repository",
  "severity": "warning",
  "claim_id": "clm_...",
  "target_file": "../outside.py",
  "error_type": "PathContainmentError",
  "message": "Repository path was rejected by containment policy; no file or evidence was read."
}
```

The `.env.example` rejection uses `code="repository_file_path_rejected"` and
`target_file=".env.example"`. Diagnostics never contain file content or the
resolved outside path; the exception text is deliberately not copied into the
record. `collect_evidence_for_claims()` clears diagnostics at the start of each
batch; `clear_path_diagnostics()` is available for direct `collect_for_claim()`
users.

---

## 3. Callers inspected and tested

| Caller | Path | Tested by |
|---|---|---|
| `EvidenceCollector.collect_for_claim` | direct | New valid/missing/traversal/absolute/symlink tests |
| `EvidenceCollector.collect_evidence_for_claims` | batch | New mixed-batch test (also proves batch reset) |
| `VerificationEngine.verify_finding` | review/verification pipeline | New valid, missing and unsafe-finding tests |
| `VerificationEngine.verify_report` | report pipeline | New valid + missing report test |
| `code_graph.evidence.verify_claim_with_graph` | Code Graph adapter | New valid (`SUPPORTED`) and unsafe (`INCONCLUSIVE`) tests |
| Existing direct test caller | `tests/test_verification_engine.py` | 3/3 passed unchanged |
| `tests/test_phase11_12_e2e.py` boundary test | public API + tool | 19 passed, 1 symlink skip |

Other similarly named classes are **not** this collector and were not treated
as affected callers:

- `backend/app/agent/loop94.py::EvidenceCollector` — a separate local class.
- `backend/app/services/evidence_collector.py` — a separate service wrapper.
- `backend/app/services/deterministic_verifier.py::verify_claim` — a separate
  verifier that does not use `EvidenceCollector`.

No caller of the shared `EvidenceCollector` bypasses `collect_for_claim`.

---

## 4. Security behavior before and after

| Scenario | Before | After |
|---|---|---|
| Valid relative file (`src/safe.py`) | Read; corroborating CODE evidence | **Unchanged**; read, evidence and snippets collected |
| Missing in-repository file (`src/missing.py`) | Non-corroborating STRUCTURE item: "does not exist" | **Unchanged**; same item, verifier still returns `FALSE` |
| `../outside.py` (existing outside file) | Read outside root; outside content returned as corroborating evidence | **Rejected**; no evidence items; `path_traversal` diagnostic |
| Absolute external path | Read outside root; outside content returned | **Rejected**; `absolute_path` diagnostic |
| Absolute path pointing inside root | Read (path happened to be safe) | **Rejected by policy**; `absolute_path` diagnostic |
| Symlink in repo → outside file | Followed by `exists()` / `read_text()`; outside content read | **Rejected** by `resolve_repository_path`; `outside_repository` diagnostic |
| Symlinked `.env.example` → outside file | Read during `CONFIG_KEY_MISSING` collection | **Rejected**; no configuration evidence; `repository_file_path_rejected` diagnostic |
| Invalid target in a `FILE_EXISTS` claim | Could be reported `TRUE` from an outside file | No supporting evidence; verification becomes `UNCERTAIN` / Code Graph `INCONCLUSIVE` |
| Diagnostics for violations | None (silent) | Structured list with code, reason, severity, claim id, target and error type |

The guard uses the existing shared `app.core.path_guard.resolve_repository_path`,
which rejects empty paths, POSIX/Windows/UNC absolute paths, any `..`
component, and symlink escapes after resolution. The claim's original relative
path is still used as evidence provenance, so valid evidence metadata is
unchanged.

**Code Graph policy alignment:** `verify_claim_with_graph` retains its
`_claim_target_contained` pre-check. It calls the same
`resolve_repository_path` function, records
`claim_target_within_repository`, and never hands an unsafe target to the
collector. The collector independently enforces the identical policy for all
other callers, so a new caller cannot bypass containment by skipping the graph
adapter.

---

## 5. Exact test results

All results are from the post-fix working tree.

### New regression suite

```
cd backend && python -m pytest tests/test_evidence_collector_security.py -q
9 passed, 2 skipped in 1.44s
```

The two skips are the symlink tests (`WinError 1314`, privilege not held on
this Windows host). The same file contains 10 tests total: 8 executed, 2
environment-gated.

### Affected suites

```
tests/test_verification_engine.py                 3 passed
tests/code_graph                                  286 passed, 4 skipped
tests/test_phase11_11_integration.py + 11.12      66 passed, 1 skipped
tests/test_phase6_evidence_evaluation.py          8 passed
tests/test_review_integration.py + test_phase3_agent.py
                                                  20 passed, 2 failed (pre-existing)
```

Combined targeted run:

```
python -m pytest tests/test_evidence_collector_security.py \
  tests/test_verification_engine.py tests/code_graph \
  tests/test_phase11_11_integration.py tests/test_phase11_12_e2e.py \
  tests/test_phase6_evidence_evaluation.py -q
372 passed, 7 skipped in 24.27s
```

The two failures in the review/agent selection are the known pre-existing CLI
branding/entry-point cases:

- `tests/test_phase3_agent.py::test_cli_init_runs_on_temp_workspace`
- `tests/test_review_integration.py::TestReviewIntegration::test_review_command_still_works`

### Full backend suite

```
cd backend && python -m pytest -q
16 failed, 911 passed, 8 skipped, 65 warnings in 588.49s (0:09:48)
```

The 16 failures are exactly the pre-existing set from the Phase 12.1 baseline:
15 KiteHut-vs-RepoLens CLI/branding and console-entry-point failures, plus
`tests/test_phase8_6_rag.py::TestRagPipeline::test_answer_preserves_provenance`
(Ollama timeout). No new failure was introduced.

The 8 skips comprise the 7 environment-gated symlink/named-pipe skips seen in
the targeted run (including the 2 new symlink tests) plus one additional
full-run Ollama-availability skip. `tests/test_phase8_6_rag.py` passes
`33 passed` when run alone (193.20s), so the extra skip is environment/load
related, not a regression. The pass/skip split differs from the Phase 12.1
baseline accordingly; the failure set does not.

No test was weakened, deleted or skipped to make the change pass.

---

## 6. Compatibility assessment

**Preserved:**

- Valid repository-relative paths resolve and read exactly as before.
- Missing in-repository files still produce the non-corroborating
  `STRUCTURE` evidence item and still verify as `FALSE` when the claim asserts
  existence.
- Normal `verify_finding` / `verify_report` statuses are unchanged for real and
  missing findings (`TRUE` and `FALSE` respectively in the new tests).
- Code Graph valid claims remain `SUPPORTED`; unsafe claims remain
  `INCONCLUSIVE` with no evidence.
- `collect_for_claim` and `collect_evidence_for_claims` retain their existing
  return types (`List[EvidenceItem]`); the change is additive.
- `VerificationEngine.verify_claim` is untouched and receives the same evidence
  contract.
- Existing evidence metadata, snippets, source paths and verifier routing are
  unchanged for valid paths.

**Intentionally changed:**

- Absolute paths are now rejected even when they point inside the repository.
  This matches the stated policy ("reject absolute paths") and is necessary to
  avoid callers relying on host-specific absolute forms. Repository findings
  and the Code Graph adapter use repository-relative paths, so the inspected
  callers are unaffected.
- A `.env.example` that escapes via symlink no longer contributes configuration
  evidence; the claim falls back to whatever other valid evidence exists
  (typically `PARTIALLY_TRUE` or `UNCERTAIN` for `CONFIG_KEY_MISSING`).

**Additive API:** `path_diagnostics` and `clear_path_diagnostics()`.

---

## 7. Remaining risks

1. **Symlink execution not verified on this host.** Two new symlink tests and
   the pre-existing code-graph symlink tests skip with `WinError 1314` because
   the Windows process lacks symlink-creation privilege. The guard's POSIX
   symlink behavior is covered by the existing path-guard tests and by
   inspection, and will run on a POSIX CI host. This is a coverage gap, not a
   known defect.
2. **Diagnostics are collector-level.** `verify_finding` does not copy
   `path_diagnostics` into `Finding` (the model has no diagnostics field), and
   CLI/report output does not yet display them. Callers and tests can read
   `engine.collector.path_diagnostics`; surfacing them in reports is a
   follow-up, not required for containment.
3. **TOCTOU after resolution.** The guard resolves symlinks before the read; a
   local attacker who can replace the resolved file between resolution and
   `read_text` could still race the read. This is a local-filesystem race
   outside the threat model addressed here.
4. **Separate collectors remain outside this boundary.** The classes in
   `app/agent/loop94.py` and `app/services/evidence_collector.py`, and the
   review `EvidenceVerifier`, do not use this collector; their path handling
   was not changed and is not covered by this phase.
5. **Diagnostics accumulation on direct single-claim calls.** `collect_for_claim`
   appends diagnostics until explicitly cleared; batch collection resets them.
   Callers that reuse a collector for repeated single calls should call
   `clear_path_diagnostics()` when they need per-call diagnostics.
6. **Absolute-path compatibility.** Any out-of-tree caller that previously
   supplied absolute in-root paths will now receive no evidence plus a
   diagnostic. No such caller exists in the inspected codebase, but this is a
   deliberate policy change to document.

---

## 8. PASS / FAIL / NOT TESTED matrix

| Check | Result | Evidence |
|---|---|---|
| Valid in-repository relative source file | **PASS** | New test: evidence collected, snippet contains source text, no diagnostics |
| Missing in-repository file | **PASS** | New test: non-corroborating `STRUCTURE` item, verifier `FALSE`, no diagnostics |
| Parent-directory traversal (`../`) | **PASS** | New test: no items, `path_traversal` diagnostic |
| Absolute external path | **PASS** | New test: no items, `absolute_path` diagnostic |
| Absolute path inside repository | **PASS** | New test: rejected by policy, `absolute_path` diagnostic |
| Symlink pointing outside repository | **NOT TESTED (runtime on this host)** | Test skips: `WinError 1314`; guard path inspected and POSIX coverage pending |
| Symlinked `.env.example` escape | **NOT TESTED (runtime on this host)** | Test skips for the same privilege reason; code path guarded |
| Mixed valid + traversal + missing + absolute batch | **PASS** | New test: only valid/missing evidence, two diagnostics, batch reset proven |
| `VerificationEngine.verify_finding` valid/missing | **PASS** | New test: `TRUE` / `FALSE`, no diagnostics |
| `VerificationEngine.verify_report` mixed findings | **PASS** | New test: `TRUE` / `FALSE` preserved |
| Unsafe finding target through `verify_finding` | **PASS** | New test: `UNCERTAIN`, empty evidence, diagnostic present |
| Code Graph valid claim compatibility | **PASS** | New test: `SUPPORTED` |
| Code Graph unsafe claim containment | **PASS** | New test: `INCONCLUSIVE`, `claim_target_within_repository=False`, no evidence |
| Existing verification/evidence tests | **PASS** | `test_verification_engine.py` 3/3; Phase 6 8/8 |
| Code Graph suite | **PASS** | 286 passed, 4 skipped |
| Phase 11.11/11.12 integration | **PASS** | 66 passed, 1 skipped |
| Full backend suite green | **FAIL (pre-existing only)** | 911 passed, 16 failed, 8 skipped; failure set identical to Phase 12.1 |
| Database startup / migrations | **NOT TESTED (excluded)** | Not run |
| Frontend/UI | **NOT TESTED (out of scope)** | Not modified |

---

## 9. Recommendation

**PASS.** The shared collector now applies one containment policy to every
claim target and to `.env.example`; unsafe paths produce no evidence and a
structured diagnostic; valid relative paths and missing-file behavior are
preserved; and every caller of `collect_for_claim` /
`collect_evidence_for_claims` was tested. The remaining symlink runtime gap is
environmental (Windows symlink privilege) and should be covered on POSIX CI.

No release-blocking defect remains in this phase. The change is confined to the
collector, one explanatory comment in the Code Graph adapter, and the new test
file.
