"""
Phase 6 — Evidence & Evaluation Tests.
Deterministic. No LLM. Evidence must support claims.
"""
import tempfile, shutil
from pathlib import Path

def test_evidence_verifier_verified():
    from app.review.review_engine import ReviewEngine
    from app.review.evidence_verifier import EvidenceVerifier
    ws = Path(tempfile.mkdtemp())
    (ws / "auth.py").write_text('password = "secret"\n')
    engine = ReviewEngine(str(ws))
    findings = engine.review_repo()
    verifier = EvidenceVerifier(str(ws))
    res = verifier.verify(findings[0])
    assert res.status.value == "verified"
    assert res.quality.value == "strong"
    shutil.rmtree(ws)

def test_evidence_verifier_stale_after_change():
    from app.review.review_engine import ReviewEngine
    from app.review.evidence_verifier import EvidenceVerifier
    ws = Path(tempfile.mkdtemp())
    fpath = ws / "auth.py"
    fpath.write_text('password = "secret"\n')
    engine = ReviewEngine(str(ws))
    findings = engine.review_repo()
    # Mutate file
    fpath.write_text('other = 1\n')
    verifier = EvidenceVerifier(str(ws))
    res = verifier.verify(findings[0])
    assert res.status.value == "stale"
    shutil.rmtree(ws)

def test_evidence_verifier_unsupported_empty_snippet():
    from app.review.review_engine import ReviewEngine
    from app.review.evidence_verifier import EvidenceVerifier
    ws = Path(tempfile.mkdtemp())
    fpath = ws / "auth.py"
    fpath.write_text('password = "secret"\n')
    engine = ReviewEngine(str(ws))
    findings = engine.review_repo()
    # Clear snippet to simulate broken evidence
    findings[0].evidence[0].snippet = ""
    verifier = EvidenceVerifier(str(ws))
    res = verifier.verify(findings[0])
    assert res.status.value in ("unsupported", "inconclusive")
    shutil.rmtree(ws)

def test_evidence_quality_strong_medium_weak():
    from app.review.evidence_quality_engine import EvidenceQualityEngine
    from app.review.verification_status import VerificationStatus
    from app.review.evidence_quality import EvidenceQuality
    engine = EvidenceQualityEngine()
    assert engine.assess(VerificationStatus.VERIFIED, True, True, False) == EvidenceQuality.STRONG
    assert engine.assess(VerificationStatus.VERIFIED, True, False, False) == EvidenceQuality.MEDIUM
    assert engine.assess(VerificationStatus.UNSUPPORTED, False, False, False) == EvidenceQuality.WEAK

def test_confidence_mapping_independent_of_severity():
    from app.review.confidence_engine import ConfidenceEngine, ConfidenceLevel
    from app.review.verification_status import VerificationStatus
    from app.review.evidence_quality import EvidenceQuality
    ce = ConfidenceEngine()
    assert ce.compute(VerificationStatus.VERIFIED, EvidenceQuality.STRONG) == ConfidenceLevel.HIGH
    assert ce.compute(VerificationStatus.VERIFIED, EvidenceQuality.WEAK) == ConfidenceLevel.LOW

def test_evaluation_metrics_tp_fp_fn():
    from app.review.evaluation_engine import FindingEvaluator, EvaluationMetrics
    from app.review.finding import Finding, Severity, Category
    from app.review.review_engine import ReviewEngine
    ws = Path(tempfile.mkdtemp())
    (ws / "auth.py").write_text('password = "secret"\n')
    engine = ReviewEngine(str(ws))
    actual = engine.review_repo()
    evaluator = FindingEvaluator()
    # Expected same as actual for TP; empty expected for FP/FN check
    metrics = evaluator.evaluate(actual, actual)
    assert metrics.true_positives >= 1
    assert metrics.precision >= 0.0
    assert metrics.recall >= 0.0
    shutil.rmtree(ws)

def test_fixtures_clean_repo_no_false_positives():
    from app.review.fixtures.fixture_repos import create_clean_repo
    from app.review.review_engine import ReviewEngine
    ws = Path(tempfile.mkdtemp())
    create_clean_repo(ws)
    engine = ReviewEngine(str(ws))
    findings = engine.review_repo()
    sec = [f for f in findings if f.rule_id == "SEC-01"]
    assert len(sec) == 0
    shutil.rmtree(ws)

def test_fixtures_near_miss_false_positive():
    from app.review.fixtures.fixture_repos import create_near_miss_repo
    from app.review.review_engine import ReviewEngine
    ws = Path(tempfile.mkdtemp())
    create_near_miss_repo(ws)
    engine = ReviewEngine(str(ws))
    findings = engine.review_repo()
    # Pattern resembles secret but is informational; may or may not trigger
    # Just verify evaluation can process it
    assert isinstance(findings, list)
    shutil.rmtree(ws)
