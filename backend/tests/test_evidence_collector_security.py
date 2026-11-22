"""Phase 12.2 — shared EvidenceCollector repository containment.

Covers valid, missing, traversal, absolute and symlink targets through the
collector, the batch entry point, the review/verification pipeline and the Code
Graph verification entry point.
"""

import os
from pathlib import Path

import pytest

from app.code_graph.evidence import EvidenceStatus, verify_claim_with_graph
from app.intelligence.models.findings import (
    Finding,
    FindingCategory,
    FindingSeverity,
    IntelligenceReport,
)
from app.verification.collectors.evidence_collector import EvidenceCollector
from app.verification.models.claim import ClaimType, ExtractedClaim
from app.verification.models.evidence import EvidenceType
from app.verification.models.truth import TruthStatus
from app.verification.verification_engine import VerificationEngine

SECRET = "sk_live_phase122_secret"


def _workspace(tmp_path: Path):
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "safe.py").write_text(
        f"API_KEY = '{SECRET}'\n", encoding="utf-8"
    )
    outside = tmp_path / "outside.py"
    outside.write_text(f"OUTSIDE = '{SECRET}_outside'\n", encoding="utf-8")
    return repo, outside


def _claim(
    target,
    *,
    claim_id="clm_test",
    claim_type=ClaimType.FILE_EXISTS,
    line=1,
    pattern=None,
):
    return ExtractedClaim(
        claim_id=claim_id,
        claim_type=claim_type,
        statement=f"Claim about {target}.",
        target_file=target,
        target_line=line,
        expected_pattern=pattern,
    )


def _finding(title, file_path, *, snippet=SECRET):
    return Finding(
        category=FindingCategory.SECURITY,
        severity=FindingSeverity.CRITICAL,
        title=title,
        description="Hardcoded API secret in source",
        file_path=file_path,
        line_number=1,
        code_snippet=snippet,
    )


def test_valid_relative_source_file_is_collected(tmp_path):
    repo, _ = _workspace(tmp_path)
    collector = EvidenceCollector(str(repo))

    items = collector.collect_for_claim(
        _claim("src/safe.py", claim_type=ClaimType.SECRET_PATTERN_MATCH)
    )

    assert items
    assert all(item.is_corroborating for item in items)
    assert any(SECRET in (item.snippet or "") for item in items)
    assert collector.path_diagnostics == []


def test_missing_in_repository_file_keeps_missing_evidence(tmp_path):
    repo, _ = _workspace(tmp_path)
    collector = EvidenceCollector(str(repo))
    claim = _claim("src/missing.py")

    items = collector.collect_for_claim(claim)

    assert collector.path_diagnostics == []
    assert len(items) == 1
    assert items[0].evidence_type == EvidenceType.STRUCTURE
    assert items[0].is_corroborating is False
    assert "does not exist" in items[0].description

    verdict = VerificationEngine(str(repo)).verify_claim(claim, items)
    assert verdict.status == TruthStatus.FALSE


def test_parent_directory_traversal_is_rejected(tmp_path):
    repo, _ = _workspace(tmp_path)
    collector = EvidenceCollector(str(repo))

    items = collector.collect_for_claim(
        _claim("../outside.py", claim_id="clm_traversal")
    )

    assert items == []
    assert len(collector.path_diagnostics) == 1
    diagnostic = collector.path_diagnostics[0]
    assert diagnostic["code"] == "claim_target_path_rejected"
    assert diagnostic["reason"] == "path_traversal"
    assert diagnostic["claim_id"] == "clm_traversal"
    assert diagnostic["target_file"] == "../outside.py"
    assert SECRET not in repr(items)


def test_absolute_paths_are_rejected_even_inside_repository(tmp_path):
    repo, outside = _workspace(tmp_path)
    collector = EvidenceCollector(str(repo))

    # Absolute external path and absolute path that happens to point inside
    # the repository are both rejected by the shared policy.
    for target in (str(outside), str(repo / "src" / "safe.py")):
        assert collector.collect_for_claim(_claim(target)) == []

    assert len(collector.path_diagnostics) == 2
    assert {d["reason"] for d in collector.path_diagnostics} == {"absolute_path"}
    assert all(d["code"] == "claim_target_path_rejected" for d in collector.path_diagnostics)


def test_symlink_escape_is_rejected(tmp_path):
    repo, outside = _workspace(tmp_path)
    link = repo / "escape.py"
    try:
        os.symlink(outside, link)
    except (OSError, NotImplementedError) as error:  # pragma: no cover
        pytest.skip(f"Symlinks are not available in this environment: {error}")

    collector = EvidenceCollector(str(repo))
    items = collector.collect_for_claim(
        _claim("escape.py", claim_type=ClaimType.SECRET_PATTERN_MATCH)
    )

    assert items == []
    assert len(collector.path_diagnostics) == 1
    assert collector.path_diagnostics[0]["reason"] == "outside_repository"
    assert SECRET not in repr(items)


def test_config_template_collection_preserves_existing_behavior(tmp_path):
    repo, _ = _workspace(tmp_path)
    claim = ExtractedClaim(
        claim_id="clm_config",
        claim_type=ClaimType.CONFIG_KEY_MISSING,
        statement="DATABASE_URL is missing from .env.example.",
        target_file="src/safe.py",
        context_data={"env_key": "DATABASE_URL"},
    )
    collector = EvidenceCollector(str(repo))

    missing_template = collector.collect_for_claim(claim)
    assert any(
        item.evidence_type == EvidenceType.CONFIGURATION
        and item.is_corroborating
        and "missing from repository root" in item.description
        for item in missing_template
    )

    (repo / ".env.example").write_text("OTHER_KEY=1\n", encoding="utf-8")
    absent_key = collector.collect_for_claim(claim)
    assert any(
        item.evidence_type == EvidenceType.CONFIGURATION
        and "not defined" in item.description
        for item in absent_key
    )

    (repo / ".env.example").write_text(
        "DATABASE_URL=postgres://local\n", encoding="utf-8"
    )
    present_key = collector.collect_for_claim(claim)
    assert not any(
        item.evidence_type == EvidenceType.CONFIGURATION for item in present_key
    )
    assert collector.path_diagnostics == []


def test_symlinked_env_template_cannot_escape_repository(tmp_path):
    repo, outside = _workspace(tmp_path)
    link = repo / ".env.example"
    try:
        os.symlink(outside, link)
    except (OSError, NotImplementedError) as error:  # pragma: no cover
        pytest.skip(f"Symlinks are not available in this environment: {error}")

    collector = EvidenceCollector(str(repo))
    claim = ExtractedClaim(
        claim_id="clm_env",
        claim_type=ClaimType.CONFIG_KEY_MISSING,
        statement="Environment key is missing.",
        target_file="src/safe.py",
        context_data={"env_key": "MISSING_KEY"},
    )

    items = collector.collect_for_claim(claim)

    assert not any(
        item.evidence_type == EvidenceType.CONFIGURATION and item.is_corroborating
        for item in items
    )
    assert any(
        diagnostic["code"] == "repository_file_path_rejected"
        and diagnostic["target_file"] == ".env.example"
        for diagnostic in collector.path_diagnostics
    )


def test_mixed_batch_preserves_valid_and_missing_evidence(tmp_path):
    repo, outside = _workspace(tmp_path)
    collector = EvidenceCollector(str(repo))

    # Seed a diagnostic to prove batch collection resets diagnostics.
    collector.collect_for_claim(_claim("../outside.py", claim_id="clm_old"))
    assert len(collector.path_diagnostics) == 1

    claims = [
        _claim(
            "src/safe.py",
            claim_id="clm_valid",
            claim_type=ClaimType.SECRET_PATTERN_MATCH,
        ),
        _claim("../outside.py", claim_id="clm_traversal"),
        _claim("src/missing.py", claim_id="clm_missing"),
        _claim(str(outside), claim_id="clm_absolute"),
    ]
    items = collector.collect_evidence_for_claims(claims)

    assert any(SECRET in (item.snippet or "") for item in items)
    assert any(
        item.evidence_type == EvidenceType.STRUCTURE and not item.is_corroborating
        for item in items
    )
    assert all("outside.py" not in (item.source_file or "") for item in items)
    assert {d["claim_id"] for d in collector.path_diagnostics} == {
        "clm_traversal",
        "clm_absolute",
    }
    assert len(collector.path_diagnostics) == 2


def test_verification_engine_preserves_normal_statuses(tmp_path):
    repo, _ = _workspace(tmp_path)
    engine = VerificationEngine(str(repo))

    real = engine.verify_finding(_finding("Hardcoded API key", "src/safe.py"))
    assert real.truth_status == TruthStatus.TRUE.value
    assert real.evidence_items

    missing = engine.verify_finding(_finding("Ghost secret", "src/missing.py"))
    assert missing.truth_status == TruthStatus.FALSE.value
    assert engine.collector.path_diagnostics == []

    report = IntelligenceReport(
        repository_path=str(repo),
        findings=[
            _finding("Real secret in report", "src/safe.py"),
            _finding("Ghost secret in report", "src/missing.py"),
        ],
    )
    verified = engine.verify_report(report)
    statuses = {finding.title: finding.truth_status for finding in verified.findings}
    assert statuses["Real secret in report"] == TruthStatus.TRUE.value
    assert statuses["Ghost secret in report"] == TruthStatus.FALSE.value


def test_verification_engine_rejects_unsafe_finding_target(tmp_path):
    repo, _ = _workspace(tmp_path)
    engine = VerificationEngine(str(repo))

    verified = engine.verify_finding(
        _finding("Hardcoded API key outside", "../outside.py")
    )

    assert verified.truth_status == TruthStatus.UNCERTAIN.value
    assert verified.evidence_items == []
    assert engine.collector.path_diagnostics
    assert all(
        diagnostic["code"] == "claim_target_path_rejected"
        for diagnostic in engine.collector.path_diagnostics
    )
    assert SECRET not in repr(verified.evidence_items)


def test_code_graph_verification_entry_point_keeps_containment(tmp_path):
    repo, _ = _workspace(tmp_path)
    pattern = f"API_KEY = '{SECRET}'"

    valid = verify_claim_with_graph(
        _claim(
            "src/safe.py",
            claim_id="clm_graph_valid",
            claim_type=ClaimType.CODE_CONTAINS_PATTERN,
            pattern=pattern,
        ),
        repo,
    )
    assert valid.status == EvidenceStatus.SUPPORTED

    unsafe = verify_claim_with_graph(
        _claim(
            "../outside.py",
            claim_id="clm_graph_unsafe",
            claim_type=ClaimType.CODE_CONTAINS_PATTERN,
            pattern=pattern,
        ),
        repo,
    )
    assert unsafe.status == EvidenceStatus.INCONCLUSIVE
    assert unsafe.bundle.diagnostics["claim_target_within_repository"] is False
    assert unsafe.bundle.evidence_items == []
    assert SECRET not in repr(unsafe.bundle.evidence_items)
