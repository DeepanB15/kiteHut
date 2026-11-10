"""
Unit and Integration Tests for Trust & Verification Engine Subsystem (Layer 5).
"""

from pathlib import Path
from app.context.project_map.project_map import ProjectMapBuilder
from app.intelligence.models.findings import Finding, FindingCategory, FindingSeverity, IntelligenceReport
from app.verification.classification.truth_classifier import TruthClassifier
from app.verification.collectors.evidence_collector import EvidenceCollector
from app.verification.extractors.claim_extractor import ClaimExtractor
from app.verification.models.claim import ClaimType
from app.verification.models.evidence import EvidenceType
from app.verification.models.truth import TruthStatus, VerificationVerdict
from app.verification.verification_engine import VerificationEngine


def test_claim_extractor_and_evidence_collector(temp_workspace):
    """Verify claim extraction from findings and evidence collection from disk."""
    ws = temp_workspace
    vuln_path = ws / "src" / "vuln.py"
    vuln_path.write_text(
        "api_secret = 'sk_live_9988776655443322'\n"
        "cursor.execute(f'SELECT * FROM users WHERE id = {user_id}')\n",
        encoding="utf-8",
    )

    finding = Finding(
        category=FindingCategory.SECURITY,
        severity=FindingSeverity.CRITICAL,
        title="Hardcoded API Secret Detected",
        description="Plaintext sk_live_ token in source file",
        file_path="src/vuln.py",
        line_number=1,
        code_snippet="api_secret = 'sk_live_9988776655443322'",
    )

    extractor = ClaimExtractor()
    claims = extractor.extract_claims(finding)

    assert len(claims) >= 2
    claim_types = {c.claim_type for c in claims}
    assert ClaimType.FILE_EXISTS in claim_types
    assert ClaimType.SECRET_PATTERN_MATCH in claim_types

    collector = EvidenceCollector(str(ws))
    evidence_items = collector.collect_evidence_for_claims(claims)

    assert len(evidence_items) >= 2
    assert any(e.evidence_type == EvidenceType.CODE for e in evidence_items)
    assert any("sk_live_" in (e.snippet or "") for e in evidence_items)


def test_verification_engine_verifies_real_and_false_claims(temp_workspace):
    """Verify that valid findings are classified as TRUE and hallucinated findings as FALSE."""
    ws = temp_workspace
    # Real file with secret
    secret_file = ws / "src" / "secret.py"
    secret_file.write_text("API_KEY = 'sk_live_abcdef1234567890'\n", encoding="utf-8")

    engine = VerificationEngine(str(ws))

    # 1. Real Finding
    real_finding = Finding(
        category=FindingCategory.SECURITY,
        severity=FindingSeverity.CRITICAL,
        title="Hardcoded Stripe Secret",
        description="Hardcoded sk_live_ token",
        file_path="src/secret.py",
        line_number=1,
        code_snippet="API_KEY = 'sk_live_abcdef1234567890'",
    )

    verified_real = engine.verify_finding(real_finding)
    assert verified_real.truth_status == TruthStatus.TRUE.value
    assert verified_real.confidence >= 80.0
    assert verified_real.score > 70.0
    assert verified_real.priority in {"P0", "P1"}
    assert len(verified_real.evidence_items) > 0

    # 2. Hallucinated Finding (target file does not exist)
    fake_finding = Finding(
        category=FindingCategory.SECURITY,
        severity=FindingSeverity.HIGH,
        title="Ghost Vulnerability",
        description="Non-existent file flagged",
        file_path="src/does_not_exist.py",
        line_number=10,
    )

    verified_fake = engine.verify_finding(fake_finding)
    assert verified_fake.truth_status == TruthStatus.FALSE.value
    assert verified_fake.lifecycle_status == "FALSE_POSITIVE"


def test_verify_report_prioritization_and_sorting(temp_workspace):
    """Verify that verify_report scores, sorts, and enriches entire IntelligenceReport."""
    ws = temp_workspace
    (ws / "src" / "main.py").write_text("api_key = 'sk_live_123456'\n", encoding="utf-8")

    engine = VerificationEngine(str(ws))

    findings = [
        Finding(
            category=FindingCategory.QUALITY,
            severity=FindingSeverity.LOW,
            title="Slightly long function",
            description="Function is 30 lines long",
            file_path="src/main.py",
            line_number=1,
        ),
        Finding(
            category=FindingCategory.SECURITY,
            severity=FindingSeverity.CRITICAL,
            title="Exposed API Secret",
            description="Hardcoded sk_live_ key",
            file_path="src/main.py",
            line_number=1,
        ),
    ]

    report = IntelligenceReport(
        repository_path=str(ws),
        findings=findings,
    )

    verified_report = engine.verify_report(report)

    # Top priority finding must be the Critical Security finding (P0/P1)
    assert len(verified_report.findings) == 2
    top_finding = verified_report.findings[0]
    assert top_finding.category == FindingCategory.SECURITY
    assert top_finding.score > verified_report.findings[1].score
