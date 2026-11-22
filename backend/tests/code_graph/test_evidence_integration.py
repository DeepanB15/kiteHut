"""Phase 11.10 — focused tests for Code Graph evidence integration.

The tests build real Code Graphs over a copy of the committed
``tests/fixtures/code_graph/sample_project`` fixture and exercise the graph ->
evidence -> existing verification engine path: supported, unsupported,
inconclusive, stale, ambiguous, graph-unavailable fallback and provenance.
"""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

import pytest

from app.code_graph import CodeGraphBuilder
from app.code_graph.evidence import (
    EvidenceStatus,
    collect_graph_evidence,
    verify_claim_with_graph,
)
from app.verification.models.claim import ClaimType, ExtractedClaim
from app.verification.models.evidence import EvidenceItem, EvidenceType
from app.verification.models.truth import TruthStatus
from app.verification.verification_engine import VerificationEngine


FIXTURE_ROOT = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "code_graph"
    / "sample_project"
)


def _copy_fixture(tmp_path: Path) -> Path:
    target = tmp_path / "repo"
    shutil.copytree(FIXTURE_ROOT, target)
    return target


def _build_graph(root: Path):
    result = CodeGraphBuilder(str(root)).build()
    assert result.graph is not None, "fixture graph must build"
    return result.graph


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    return _copy_fixture(tmp_path)


@pytest.fixture
def graph(repo: Path):
    return _build_graph(repo)


def _main_call_claim() -> ExtractedClaim:
    return ExtractedClaim(
        claim_type=ClaimType.GENERIC,
        statement="main calls run in pkg/core.py",
        target_file="pkg/core.py",
        target_line=12,
        expected_pattern="return run()",
    )


# ------------------------------------------------------- supported -------


def test_supported_claim_with_fresh_source_evidence(repo: Path, graph) -> None:
    outcome = verify_claim_with_graph(_main_call_claim(), repo, graph=graph)

    assert outcome.status is EvidenceStatus.SUPPORTED
    assert outcome.verdict.status is TruthStatus.TRUE

    supporting = [
        span
        for span in outcome.bundle.spans
        if span.exact_match and span.claim_relevant
    ]
    assert supporting, "expected an exact source-span match"
    assert all(not span.stale and not span.ambiguous for span in supporting)
    assert outcome.bundle.diagnostics["supporting_count"] >= 1


def test_claim_naming_a_symbol_is_supported_by_its_declaration(repo: Path, graph) -> None:
    claim = ExtractedClaim(
        claim_type=ClaimType.GENERIC,
        statement="helper is defined in the utility module.",
        expected_pattern="def helper():",
    )

    outcome = verify_claim_with_graph(claim, repo, graph=graph)

    assert outcome.status is EvidenceStatus.SUPPORTED
    symbol_span = next(
        span
        for span in outcome.bundle.spans
        if span.relationship == "named_symbol"
    )
    assert symbol_span.symbol_name == "helper"
    assert symbol_span.relative_path == "pkg/util.py"
    assert symbol_span.declaration_match is True


# ------------------------------------------------------- unsupported -----


def test_unsupported_claim_targeting_a_missing_file(repo: Path, graph) -> None:
    claim = ExtractedClaim(
        claim_type=ClaimType.FILE_EXISTS,
        statement="The module pkg/ghost.py exists in the repository.",
        target_file="pkg/ghost.py",
    )

    outcome = verify_claim_with_graph(claim, repo, graph=graph)

    assert outcome.status is EvidenceStatus.UNSUPPORTED
    assert outcome.verdict.status is TruthStatus.FALSE
    assert outcome.bundle.diagnostics["missing_count"] == 1
    assert any(
        span.missing and span.relative_path == "pkg/ghost.py"
        for span in outcome.bundle.spans
    )


def test_missing_source_for_pattern_claim_is_inconclusive(repo: Path) -> None:
    # A missing source file is insufficient evidence for a content claim; it
    # must not be reported as a direct contradiction.
    claim = ExtractedClaim(
        claim_type=ClaimType.SECRET_PATTERN_MATCH,
        statement="A hardcoded API secret is stored in src/config.py.",
        target_file="src/config.py",
        expected_pattern="API_SECRET = 'sk_live_abcdef'",
    )

    outcome = verify_claim_with_graph(claim, repo)

    assert outcome.status is EvidenceStatus.INCONCLUSIVE
    assert outcome.verdict.status is TruthStatus.FALSE
    missing = next(span for span in outcome.bundle.spans if span.missing)
    assert missing.relative_path == "src/config.py"
    # Absence is not forwarded as a refuting item for content claims.
    assert outcome.bundle.evidence_items == []


# ------------------------------------------------------- inconclusive ----


def test_inconclusive_claim_without_matching_evidence(repo: Path, graph) -> None:
    claim = ExtractedClaim(
        claim_type=ClaimType.GENERIC,
        statement="pkg/util.py defines a document parser.",
        target_file="pkg/util.py",
        expected_pattern="def parse_document():",
    )

    outcome = verify_claim_with_graph(claim, repo, graph=graph)

    assert outcome.status is EvidenceStatus.INCONCLUSIVE
    assert not any(span.exact_match for span in outcome.bundle.spans)


def test_claim_without_source_locations_is_inconclusive(repo: Path, graph) -> None:
    claim = ExtractedClaim(
        claim_type=ClaimType.GENERIC,
        statement="The architecture follows clean boundaries.",
    )

    outcome = verify_claim_with_graph(claim, repo, graph=graph)

    assert outcome.status is EvidenceStatus.INCONCLUSIVE
    assert outcome.bundle.evidence_items == []
    assert outcome.bundle.diagnostics["evidence_count"] == 0


# ------------------------------------------------------- stale -----------


def test_stale_source_evidence_never_reports_supported(repo: Path) -> None:
    graph = _build_graph(repo)

    core_path = repo / "pkg" / "core.py"
    core_path.write_text(
        core_path.read_text(encoding="utf-8") + "\n# repository drifted\n",
        encoding="utf-8",
    )

    outcome = verify_claim_with_graph(_main_call_claim(), repo, graph=graph)

    assert outcome.status is EvidenceStatus.INCONCLUSIVE
    assert outcome.bundle.diagnostics["stale_count"] >= 1
    assert any(
        span.stale_reason == "source_hash_mismatch"
        for span in outcome.bundle.stale_spans
    )
    # Stale spans are excluded from the evidence handed to the verifiers.
    assert all(
        item.metadata["stale"] is False for item in outcome.bundle.evidence_items
    )


def test_stale_evidence_metadata_records_the_mismatch(repo: Path) -> None:
    graph = _build_graph(repo)
    graph_hash = next(
        node.content_hash
        for node in graph.files
        if node.relative_path == "pkg/util.py"
    )
    util_path = repo / "pkg" / "util.py"
    util_path.write_text(
        util_path.read_text(encoding="utf-8") + "\n# drift\n",
        encoding="utf-8",
    )

    bundle = collect_graph_evidence(_main_call_claim(), repo, graph=graph)
    stale_spans = [
        span for span in bundle.stale_spans if span.relative_path == "pkg/util.py"
    ]

    assert stale_spans, "expected a stale span for the mutated import target"
    assert all(span.stale_reason == "source_hash_mismatch" for span in stale_spans)
    assert all(span.file_content_hash != graph_hash for span in stale_spans)


# ------------------------------------------------------- ambiguous -------


def test_ambiguous_graph_relationship_is_navigation_only(repo: Path) -> None:
    (repo / "pkg" / "dupe.py").write_text(
        "def helper():\n    return 2\n", encoding="utf-8"
    )
    graph = _build_graph(repo)

    claim = ExtractedClaim(
        claim_type=ClaimType.GENERIC,
        statement="helper is defined in the utility module.",
        expected_pattern="def helper():",
    )

    outcome = verify_claim_with_graph(claim, repo, graph=graph)

    assert outcome.status is EvidenceStatus.INCONCLUSIVE
    assert outcome.bundle.diagnostics["ambiguous_count"] >= 2
    assert all(
        span.ambiguous
        for span in outcome.bundle.spans
        if span.relationship == "named_symbol"
    )
    # Ambiguous spans are never forwarded as supporting evidence.
    assert all(
        item.metadata["ambiguous"] is False
        for item in outcome.bundle.evidence_items
    )


# ---------------------------------------------- graph unavailable --------


def test_empty_existing_file_with_file_exists_is_supported(repo: Path) -> None:
    (repo / "pkg" / "empty.py").write_bytes(b"")
    graph = _build_graph(repo)

    claim = ExtractedClaim(
        claim_type=ClaimType.FILE_EXISTS,
        statement="The file pkg/empty.py exists in the repository.",
        target_file="pkg/empty.py",
    )

    outcome = verify_claim_with_graph(claim, repo, graph=graph)

    assert outcome.status is EvidenceStatus.SUPPORTED
    span = next(
        span for span in outcome.bundle.spans if span.relationship == "claim_target"
    )
    assert span.file_exists is True
    assert span.stale is False
    assert span.stale_reason is None
    assert span.line_start == 0 and span.line_end == 0
    item = next(
        item
        for item in outcome.bundle.evidence_items
        if item.source_file == "pkg/empty.py"
    )
    assert item.is_corroborating is True
    assert item.metadata["file_exists"] is True


def test_file_existence_is_independent_of_line_span(repo: Path) -> None:
    graph = _build_graph(repo)
    claim = ExtractedClaim(
        claim_type=ClaimType.FILE_EXISTS,
        statement="The file pkg/core.py exists in the repository.",
        target_file="pkg/core.py",
        target_line=9999,
    )

    outcome = verify_claim_with_graph(claim, repo, graph=graph)

    assert outcome.status is EvidenceStatus.SUPPORTED
    span = next(
        span for span in outcome.bundle.spans if span.relationship == "claim_target"
    )
    assert span.file_exists is True
    assert span.stale is True
    assert span.stale_reason == "line_span_outside_file"
    assert any(
        item.is_corroborating and item.metadata["file_exists"]
        for item in outcome.bundle.evidence_items
    )


def test_pep263_non_utf8_source_is_decoded(repo: Path) -> None:
    raw = "# -*- coding: latin-1 -*-\nNAME = 'caf\xe9'\n".encode("latin-1")
    (repo / "pkg" / "latin.py").write_bytes(raw)
    graph = _build_graph(repo)

    claim = ExtractedClaim(
        claim_type=ClaimType.CODE_CONTAINS_PATTERN,
        statement="pkg/latin.py contains the name café.",
        target_file="pkg/latin.py",
        expected_pattern="NAME = 'café'",
    )

    outcome = verify_claim_with_graph(claim, repo, graph=graph)

    assert outcome.status is EvidenceStatus.SUPPORTED
    span = next(span for span in outcome.bundle.spans if span.exact_match)
    assert "café" in span.content
    # Freshness remains a raw-byte comparison.
    assert span.file_content_hash == hashlib.sha256(raw).hexdigest()
    assert span.file_exists is True


def test_mismatched_graph_repository_context_is_not_authoritative(
    repo: Path, tmp_path: Path
) -> None:
    graph = _build_graph(repo)
    other_repo = tmp_path / "other_repo"
    shutil.copytree(repo, other_repo)

    claim = ExtractedClaim(
        claim_type=ClaimType.FILE_EXISTS,
        statement="The file pkg/util.py exists in the repository.",
        target_file="pkg/util.py",
    )

    outcome = verify_claim_with_graph(claim, other_repo, graph=graph)

    assert outcome.bundle.diagnostics["repository_context_matches"] is False
    assert outcome.bundle.diagnostics["graph_valid"] is False
    assert outcome.bundle.diagnostics["fallback_used"] is True
    assert outcome.bundle.repository_id is None
    assert outcome.status is EvidenceStatus.SUPPORTED
    assert all(
        span.relationship == "claim_target" for span in outcome.bundle.spans
    )


def test_relationship_derived_nodes_must_own_the_repository(repo: Path) -> None:
    graph = _build_graph(repo)
    run_symbol = next(
        symbol for symbol in graph.symbols if symbol.name == "run"
    )
    object.__setattr__(run_symbol, "repository_id", "other-repository")

    # The statement names only `main`, so `run` is reached solely through the
    # CALLS relationship, not through the named-symbol planner.
    claim = ExtractedClaim(
        claim_type=ClaimType.GENERIC,
        statement="main returns a value",
        target_file="pkg/core.py",
    )
    bundle = collect_graph_evidence(claim, repo, graph=graph)

    assert bundle.diagnostics["repository_identity_consistent"] is False
    # No span may be produced for the node that claims another repository.
    assert all(span.symbol_id != run_symbol.id for span in bundle.spans)
    assert any(span.navigation_only for span in bundle.spans)


def test_graph_unavailable_falls_back_to_direct_source_reads(repo: Path) -> None:
    claim = ExtractedClaim(
        claim_type=ClaimType.FILE_EXISTS,
        statement="The file pkg/util.py exists in the repository.",
        target_file="pkg/util.py",
    )

    outcome = verify_claim_with_graph(claim, repo, graph=None)

    assert outcome.status is EvidenceStatus.SUPPORTED
    assert outcome.bundle.diagnostics["graph_available"] is False
    assert outcome.bundle.diagnostics["fallback_used"] is True
    assert outcome.bundle.repository_id is None
    assert all(
        span.relationship == "claim_target" for span in outcome.bundle.spans
    )


def test_invalid_graph_schema_triggers_fallback(repo: Path, graph) -> None:
    graph.schema_version = 99

    outcome = verify_claim_with_graph(_main_call_claim(), repo, graph=graph)

    assert outcome.bundle.diagnostics["graph_available"] is True
    assert outcome.bundle.diagnostics["graph_valid"] is False
    assert outcome.bundle.diagnostics["fallback_used"] is True
    assert outcome.status is EvidenceStatus.SUPPORTED


# ------------------------------------------------------- provenance -----


def test_provenance_and_repository_identity_are_preserved(repo: Path, graph) -> None:
    bundle = collect_graph_evidence(_main_call_claim(), repo, graph=graph)

    assert bundle.repository_id == graph.repository.repository_id
    assert bundle.diagnostics["repository_identity_consistent"] is True

    graph_file = next(
        node for node in graph.files if node.relative_path == "pkg/core.py"
    )
    target_item = next(
        item
        for item in bundle.evidence_items
        if item.metadata["relationship"] == "claim_target" and item.is_corroborating
    )

    raw = (repo / "pkg" / "core.py").read_bytes()
    assert target_item.source_file == "pkg/core.py"
    assert target_item.line_number == 12
    assert target_item.snippet == "    return run()"
    assert target_item.metadata["repository_id"] == graph.repository.repository_id
    assert target_item.metadata["file_id"] == graph_file.id
    assert target_item.metadata["content_hash"] == hashlib.sha256(
        target_item.snippet.encode("utf-8")
    ).hexdigest()
    assert target_item.metadata["file_content_hash"] == hashlib.sha256(
        raw
    ).hexdigest()
    assert target_item.metadata["file_content_hash"] == graph_file.content_hash
    assert target_item.metadata["graph_navigation_only"] is False


def test_named_symbol_provenance_includes_symbol_identity(repo: Path, graph) -> None:
    claim = ExtractedClaim(
        claim_type=ClaimType.GENERIC,
        statement="helper is defined in the utility module.",
        expected_pattern="def helper():",
    )
    bundle = collect_graph_evidence(claim, repo, graph=graph)

    helper = next(
        node for node in graph.symbols if node.name == "helper"
    )
    span = next(
        span for span in bundle.spans if span.relationship == "named_symbol"
    )

    assert span.symbol_id == helper.id
    assert span.file_id == helper.file_id
    assert span.repository_id == graph.repository.repository_id
    assert span.graph_provenance["provenance_kind"] == "declaration"


def test_navigation_spans_are_labelled_navigation_only(repo: Path, graph) -> None:
    bundle = collect_graph_evidence(_main_call_claim(), repo, graph=graph)

    navigation = bundle.navigation_spans
    assert navigation, "expected caller/callee/import navigation spans"
    assert all(span.navigation_only for span in navigation)
    assert all(span.graph_provenance for span in navigation)
    assert all(not span.claim_relevant for span in navigation)
    # Navigation spans never reach the verifiers as supporting evidence.
    assert all(
        item.metadata["relationship"] in {"claim_target", "named_symbol"}
        for item in bundle.evidence_items
    )


# ----------------------------------------- existing engine regression ----


def test_existing_verification_engine_claim_entry_point(repo: Path) -> None:
    engine = VerificationEngine(str(repo))
    claim = _main_call_claim()
    item = EvidenceItem(
        evidence_type=EvidenceType.CODE,
        source_file="pkg/core.py",
        line_number=12,
        snippet="    return run()",
        description="Direct source span.",
        is_corroborating=True,
    )

    verdict = engine.verify_claim(claim, [item])

    assert verdict.status is TruthStatus.TRUE
    assert item.evidence_id in verdict.evidence_ids
