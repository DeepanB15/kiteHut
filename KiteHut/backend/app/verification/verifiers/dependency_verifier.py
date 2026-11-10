"""
Dependency Verifier for RepoLens.
"""

from typing import List
from app.verification.models.claim import ClaimType, ExtractedClaim
from app.verification.models.evidence import EvidenceItem, EvidenceType
from app.verification.models.truth import TruthStatus, VerificationVerdict
from app.verification.verifiers.base_verifier import BaseVerifier


class DependencyVerifier(BaseVerifier):
    """Verifies manifest file dependencies and pinning."""

    name: str = "dependency_verifier"

    def verify(
        self,
        claim: ExtractedClaim,
        evidence: List[EvidenceItem],
    ) -> VerificationVerdict:
        dep_evidence = [e for e in evidence if e.evidence_type == EvidenceType.DEPENDENCY and e.is_corroborating]

        if dep_evidence:
            return VerificationVerdict(
                status=TruthStatus.TRUE,
                confidence=95.0,
                explanation=dep_evidence[0].description,
                evidence_ids=[e.evidence_id for e in dep_evidence],
            )

        corroborating = [e for e in evidence if e.is_corroborating]
        if corroborating:
            return VerificationVerdict(
                status=TruthStatus.PARTIALLY_TRUE,
                confidence=70.0,
                explanation="Manifest file exists on disk.",
                evidence_ids=[e.evidence_id for e in corroborating],
            )

        return VerificationVerdict(
            status=TruthStatus.UNCERTAIN,
            confidence=30.0,
            explanation="Manifest file not found or inaccessible.",
            evidence_ids=[],
        )
