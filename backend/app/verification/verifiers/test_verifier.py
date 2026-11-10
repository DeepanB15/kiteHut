"""
Testing Coverage Verifier for RepoLens.
"""

from typing import List
from app.verification.models.claim import ClaimType, ExtractedClaim
from app.verification.models.evidence import EvidenceItem, EvidenceType
from app.verification.models.truth import TruthStatus, VerificationVerdict
from app.verification.verifiers.base_verifier import BaseVerifier


class TestVerifier(BaseVerifier):
    """Verifies test coverage claims against workspace test files."""

    __test__ = False  # Avoid pytest collecting as test class
    name: str = "test_verifier"

    def verify(
        self,
        claim: ExtractedClaim,
        evidence: List[EvidenceItem],
    ) -> VerificationVerdict:
        corroborating = [e for e in evidence if e.is_corroborating]
        test_evidence = [e for e in corroborating if e.evidence_type == EvidenceType.TEST]

        if test_evidence:
            return VerificationVerdict(
                status=TruthStatus.TRUE,
                confidence=90.0,
                explanation=test_evidence[0].description,
                evidence_ids=[e.evidence_id for e in test_evidence],
            )

        if corroborating:
            return VerificationVerdict(
                status=TruthStatus.PARTIALLY_TRUE,
                confidence=60.0,
                explanation="Source module verified, test coverage status requires dynamic test execution.",
                evidence_ids=[e.evidence_id for e in corroborating],
            )

        return VerificationVerdict(
            status=TruthStatus.UNCERTAIN,
            confidence=40.0,
            explanation="Insufficient test mapping evidence.",
            evidence_ids=[],
        )
