# RepoLens — Implementation Status

> This file is intentionally conservative. A feature is marked implemented only after the codebase is inspected and the feature is verified with tests or direct evidence.

## Status Legend

- 🟢 IMPLEMENTED — verified in the current codebase
- 🟡 PARTIAL — some implementation exists but is incomplete
- 🔵 REBUILD — old implementation exists but should move to the new architecture
- 🟠 PLANNED — required by the roadmap but not implemented
- 🔴 REMOVE/DEFER — should not be part of the current architecture
- ⚪ UNVERIFIED — source code has not yet been inspected

## Current Audit

| Feature | Status | Evidence | Action |
|---|---|---|---|
| CLI | 🟢 IMPLEMENTED | `KiteHut --help` passes; `test_cli.py` passes; Click preserved (Typer deferred) | Verify
| pyproject.toml | 🟢 IMPLEMENTED | `backend/pyproject.toml` exists; `KiteHut` console entry point works; `pip install -e .` succeeds | Verify
| Package install / console entry | 🟢 IMPLEMENTED | `KiteHut --version` returns 2.0.0; import tests pass | Verify |
| Repository scanner | ⚪ UNVERIFIED | Source audit required | Inspect |
| Language detection | ⚪ UNVERIFIED | Source audit required | Inspect |
| Framework detection | ⚪ UNVERIFIED | Source audit required | Inspect |
| Dependency detection | ⚪ UNVERIFIED | Source audit required | Inspect |
| Git awareness | ⚪ UNVERIFIED | Source audit required | Inspect |
| Code search | ⚪ UNVERIFIED | Source audit required | Inspect |
| AST / Tree-sitter | ⚪ UNVERIFIED | Source audit required | Inspect |
| Symbol extraction | ⚪ UNVERIFIED | Source audit required | Inspect |
| MCP | 🟢 IMPLEMENTED | `app/mcp/server.py` FastMCP server; 23 tools registered; `tests/test_phase2_tools.py` (22 tests) pass | Verify |
| Agent runtime | ⚪ UNVERIFIED | Source audit required | Inspect |
| LangGraph | ⚪ UNVERIFIED | Old architecture reference | Defer unless justified |
| Specialized agents | ⚪ UNVERIFIED | Source audit required | Inspect |
| Security analysis | ⚪ UNVERIFIED | Source audit required | Inspect |
| Code quality | ⚪ UNVERIFIED | Source audit required | Inspect |
| Architecture analysis | ⚪ UNVERIFIED | Source audit required | Inspect |
| Testing analysis | ⚪ UNVERIFIED | Source audit required | Inspect |
| Evidence verification | 🟢 IMPLEMENTED | `app/review/evidence_verifier.py`; `tests/test_phase6_evidence_evaluation.py` (8 tests) pass | Verified |
| Confidence scoring | 🟢 IMPLEMENTED | `app/review/confidence_engine.py`; independent of severity — asserted by test | Verified |
| Evaluation engine | 🟢 IMPLEMENTED | `app/review/evaluation_engine.py`; precision/recall/F1 metrics; matching limitation documented above | Verified |
| Patch generation | ⚪ UNVERIFIED | Source audit required | Inspect |
| File editing | ⚪ UNVERIFIED | Source audit required | Inspect |
| Test execution | ⚪ UNVERIFIED | Source audit required | Inspect |
| Self-correction | ⚪ UNVERIFIED | Source audit required | Inspect |
| Permissions / sandbox | ⚪ UNVERIFIED | Source audit required | Inspect |
| SQLite memory | ⚪ UNVERIFIED | Source audit required | Inspect |
| RAG | ⚪ UNVERIFIED | Source audit required | Inspect |
| Vector DB | ⚪ UNVERIFIED | Future architecture | Defer |
| Git automation | ⚪ UNVERIFIED | Source audit required | Inspect |
| GitHub integration | ⚪ UNVERIFIED | Source audit required | Defer / inspect |
| Continuous monitoring | ⚪ UNVERIFIED | Older architecture | Defer until core agent works |
| Dashboard | ⚪ UNVERIFIED | Older architecture | Defer |
| FastAPI | ⚪ UNVERIFIED | Older architecture | Defer unless needed |
| Docker | ⚪ UNVERIFIED | Older architecture | Defer |
| LLMOps | ⚪ UNVERIFIED | Future phase | Planned |
| Notifications | ⚪ UNVERIFIED | Older architecture | Defer |
| Quality gates | ⚪ UNVERIFIED | Future capability | Planned |
| Reports | ⚪ UNVERIFIED | Source audit required | Inspect |
| CI/CD | ⚪ UNVERIFIED | Source audit required | Inspect / defer |

## Audit Rule

Never change a status from ⚪ UNVERIFIED to 🟢 IMPLEMENTED based only on README claims.

Required evidence may include:

- source file
- function/class implementation
- passing test
- CLI command execution
- integration test
- reproducible behavior

## Phase Status

| Phase | Name | Status | Evidence |
|---|---|---|---|
| Phase 5 | Review Engine | 🟢 IMPLEMENTED | `app/review/review_engine.py`; `tests/test_phase5_review_engine.py` — 6 passed |
| Phase 6 | Evidence & Evaluation | 🟢 IMPLEMENTED | `app/review/evidence_verifier.py`, `evidence_quality_engine.py`, `confidence_engine.py`, `evaluation_engine.py`, `pipeline.py`; `tests/test_phase6_evidence_evaluation.py` — 8 passed; wired into `KiteHut review` via `app/cli/commands/review_cmd.py`; `tests/test_review_integration.py` — 8 passed |

### Phase 6 — Evidence & Evaluation (COMPLETE)

Verification state:
- `VerificationStatus.VERIFIED`
- `VerificationStatus.UNSUPPORTED`
- `VerificationStatus.STALE`
- `VerificationStatus.INCONCLUSIVE`

Evidence quality:
- `EvidenceQuality.STRONG`
- `EvidenceQuality.MEDIUM`
- `EvidenceQuality.WEAK`

Severity, evidence quality, confidence, and verification status remain **independent concepts**.

Pipeline:

    Review → Detect findings → Verify evidence → Assess quality → Assign confidence

Reporting integration:
- `KiteHut review` now runs `ReviewPipeline` and renders
  Rule | Category | Severity | Verification | Evidence | Confidence
- Existing CLI command, options, and formatting conventions preserved.

Recorded verification counts:
- Phase 6 tests: 8 passed
- Phase 5 tests: 6 passed
- Full suite: 239 passed, 0 failed
- MCP tools: 23 intact
- Regressions: 0

#### Remaining non-blocking evaluation limitation

`FindingEvaluator` currently matches findings using:

    (rule_id, source_file, line_start)

This is **not fixed**. Two findings that differ only by evidence content but share
the same rule, file, and starting line are treated as the same finding during
evaluation. The matching strategy is unchanged as of this update.

## Next Verified Phase

After the source audit, select the earliest incomplete phase from PRD.md and implement only that phase.

Recommended next phase: **Phase 7 — Controlled Code Agent**.
