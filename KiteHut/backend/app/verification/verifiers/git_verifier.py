"""
Git Context and Diff Verifier for RepoLens.
"""

from typing import List
from app.verification.models.claim import ClaimType, ExtractedClaim
from app.verification.models.evidence import EvidenceItem, EvidenceType
from app.verification.models.truth import TruthStatus, VerificationVerdict
from app.verification.verifiers.base_verifier import BaseVerifier


class GitVerifier(BaseVerifier):
    """Verifies Git diff hunks, uncommitted debug code, and changed lines."""

    name: str = "git_verifier"

    def verify(
        self,
        claim: ExtractedClaim,
        evidence: List[EvidenceItem],
    ) -> VerificationVerdict:
        git_evidence = [e for e in evidence if e.evidence_type == EvidenceType.GIT and e.is_corroborating]

        if git_evidence:
            return VerificationVerdict(
                status=TruthStatus.TRUE,
                confidence=95.0,
                explanation=git_evidence[0].description,
                evidence_ids=[e.evidence_id for e in git_evidence],
            )

        corroborating = [e for e in evidence if e.is_corroborating]
        if corroborating:
            return VerificationVerdict(
                status=TruthStatus.PARTIALLY_TRUE,
                confidence=60.0,
                explanation="File is present in repository but Git diff evidence was not directly matched.",
                evidence_ids=[e.evidence_id for e in corroborating],
            )

        return VerificationVerdict(
            status=TruthStatus.UNCERTAIN,
            confidence=30.0,
            explanation="Git workspace diff unavailable or clean.",
            evidence_ids=[],
        )
