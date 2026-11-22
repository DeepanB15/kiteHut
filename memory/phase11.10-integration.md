# Phase 11.10 — Evidence Engine Integration: Architecture

## Objective

Connect Code Graph evidence discovery to the existing verification subsystem so
AI-generated claims are checked against graph-located, real source-code
evidence — without a second evidence engine and without graph relationships
being treated as proof.

## Existing architecture reused

| Layer | Existing component | Role in 11.10 |
|---|---|---|
| Claim model | `app.verification.models.claim.ExtractedClaim` | Input proposition (`target_file`, `target_line`, `expected_pattern`, `claim_type`) |
| Evidence model | `app.verification.models.evidence.EvidenceItem` | Output evidence (path, line, snippet, `is_corroborating`, `metadata`) |
| Collector | `app.verification.collectors.evidence_collector.EvidenceCollector` | Existing repository scans, merged with graph evidence |
| Verification | `app.verification.verification_engine.VerificationEngine` + domain verifiers | Decides claim status from evidence |
| Truth | `app.verification.models.truth.TruthStatus` / `VerificationVerdict` | Existing verdict contract |
| Graph | `app.code_graph.queries` (`find_symbols`, `callers`, `callees`, `imports`, `dependents`) | Navigation only |
| Freshness | `FileNode.content_hash` / `SymbolNode.source_hash` | Staleness contract |

Phase 3 (`app/models/claim.py`, `app/models/evidence.py`,
`app/engines/truth_engine.py`, `app/services/*`) and Phase 5/6 review
(`app/review/*`) are left untouched.

## Data flow

```
ExtractedClaim (existing)
  │
  ├─ collect_graph_evidence(claim, repository_root, graph, depth)
  │    1. _plan_locations()
  │         • find_symbols()  → claim-named symbols (module symbols skipped)
  │         • claim.target_file → claim target span (target_line window or file)
  │         • callers()/callees() for anchor symbols, imports()/dependents()
  │           for anchor files, bounded by depth and MAX_LOCATIONS=8
  │    2. _read_span() per location
  │         • read file bytes from the working tree
  │         • SHA-256 of file bytes vs graph content_hash/source_hash → stale
  │         • extract exact line span, SHA-256 span content
  │         • exact_match = expected_pattern contained in span
  │         • declaration_match = `def/class <symbol>` present in span
  │         • ambiguous = duplicate bare-name identity / unresolved partial
  │           match / ResolutionKind.AMBIGUOUS edge
  │    3. _select_verification_evidence()
  │         • missing target file → corroborating=False (contradiction)
  │         • exact_match / declaration_match → corroborating=True
  │         • stale, ambiguous and navigation-only spans are NOT forwarded
  │
  ├─ engine.collector.collect_for_claim(claim)   # existing evidence, unchanged
  │
  ├─ engine.verify_claim(claim, merged_evidence) # existing domain verifier
  │
  └─ _decide_status() → exactly one of SUPPORTED / UNSUPPORTED / INCONCLUSIVE
```

## Status rules

`SUPPORTED` requires **all** of:

1. the existing verifier returned `TruthStatus.TRUE`, and
2. at least one of its evidence IDs is a fresh, unambiguous, claim-relevant
   source span that either contains the claim's asserted pattern or (for
   `FILE_EXISTS` / `AST_SYMBOL_EXISTS`) confirms the referenced file or
   declaration on disk.

`UNSUPPORTED` requires the existing verifier to return `TruthStatus.FALSE`
(produced by contradictory source evidence, e.g. an absent/unreadable target
file or an existing collector refutation).

Everything else — `UNCERTAIN`, `PARTIALLY_TRUE`, `TRUE` without source-grounded
evidence, stale-only, ambiguous-only, or empty evidence — is `INCONCLUSIVE`.

## Invariants

- Graph edges are navigation labels stored in `EvidenceItem.metadata`
  (`graph_navigation_only`), never submitted as supporting evidence.
- Staleness is detected before support: a graph snapshot hash must still equal
  the current file hash, or the span is excluded and reported in diagnostics.
- Ambiguous symbol addresses (duplicate bare names, partial-only matches,
  `AMBIGUOUS` resolution) can be navigated but never support a claim.
- Missing or invalid (`schema_version != 1`) graphs fall back to direct
  claim-target source reads; graph availability is not a prerequisite.
- Evidence IDs are deterministic (`graph_ev_<sha256[:16]>`), so repeated runs
  produce reproducible evidence sets.
- Every evidence item carries `repository_id`, `file_id`, `symbol_id`,
  `relationship`, `depth`, `content_hash`, `file_content_hash`, stale/ambiguous
  flags and edge provenance.

## Files changed

- `backend/app/code_graph/evidence.py` — new module (collector + status
  projection). Replaces the unfinished untracked draft that inferred
  support/contradiction from graph heuristics.
- `backend/app/verification/verification_engine.py` — additive
  `verification_engine.verify_claim(claim, evidence_items)` entry point;
  no existing behaviour changed.
- `backend/tests/code_graph/test_evidence_integration.py` — 15 focused tests.
- `memory/phase11.10-integration.md`, `memory/phase11.10-verdict.md`.

## Explicit non-goals honoured

No new dependency, database, migration, startup change, frontend change or
Phase 11.11 work. No existing verification logic was replaced: the module only
routes graph-collected evidence into the existing verifier and projects its
verdict onto the three required statuses.
