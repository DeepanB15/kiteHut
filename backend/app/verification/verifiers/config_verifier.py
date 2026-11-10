"""
Configuration Verifier for RepoLens.
"""

from typing import List
from app.verification.models.claim import ClaimType, ExtractedClaim
from app.verification.models.evidence import EvidenceItem, EvidenceType
from app.verification.models.truth import TruthStatus, VerificationVerdict
from app.verification.verifiers.base_verifier import BaseVerifier


class ConfigVerifier(BaseVerifier):
    """Verifies environment variables and configuration consistency."""

    name: str = "config_verifier"

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
                confidence=90.0,
                explanation="Configuration target contradicted by repository structure.",
                evidence_ids=[e.evidence_id for e in contradicting],
            )

        config_evidence = [e for e in corroborating if e.evidence_type == EvidenceType.CONFIGURATION]
        if config_evidence:
            return VerificationVerdict(
                status=TruthStatus.TRUE,
                confidence=95.0,
                explanation=config_evidence[0].description or "Verified configuration discrepancy.",
                evidence_ids=[e.evidence_id for e in config_evidence],
            )

        if corroborating:
            return VerificationVerdict(
                status=TruthStatus.PARTIALLY_TRUE,
                confidence=70.0,
                explanation="Code references environment variable, but configuration template status is uncertain.",
                evidence_ids=[e.evidence_id for e in corroborating],
            )

        return VerificationVerdict(
            status=TruthStatus.UNCERTAIN,
            confidence=30.0,
            explanation="Could not verify environment configuration claims.",
            evidence_ids=[],
        )
