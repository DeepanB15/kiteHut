"""
Code and Structure Verifier for RepoLens.
"""

from typing import List
from app.verification.models.claim import ClaimType, ExtractedClaim
from app.verification.models.evidence import EvidenceItem, EvidenceType
from app.verification.models.truth import TruthStatus, VerificationVerdict
from app.verification.verifiers.base_verifier import BaseVerifier


class CodeVerifier(BaseVerifier):
    """Verifies existence and contents of source files."""

    name: str = "code_verifier"

    def verify(
        self,
        claim: ExtractedClaim,
        evidence: List[EvidenceItem],
    ) -> VerificationVerdict:
        corroborating = [e for e in evidence if e.is_corroborating]
        contradicting = [e for e in evidence if not e.is_corroborating]

        if contradicting:
            return VerificationVerdict(
                status=TruthStatus.FALSE,
                confidence=95.0,
                explanation=f"Code claim contradicted: {contradicting[0].description}",
                evidence_ids=[e.evidence_id for e in contradicting],
            )

        if not corroborating:
            return VerificationVerdict(
                status=TruthStatus.UNCERTAIN,
                confidence=30.0,
                explanation="No verifiable code evidence collected.",
                evidence_ids=[],
            )

        # File and snippet verified
        return VerificationVerdict(
            status=TruthStatus.TRUE,
            confidence=90.0,
            explanation="Source file and line structure verified directly from repository on disk.",
            evidence_ids=[e.evidence_id for e in corroborating],
        )
