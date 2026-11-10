"""
Base Verifier.

Abstract base class for all deterministic verification rules.
Phase 3, Step 17.
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import List

from app.models.claim import Claim
from app.models.evidence import Evidence, NEUTRAL
from app.models.verification import VerificationResult


class BaseVerifier(ABC):
    """
    Base class for deterministic verifiers.

    Each verifier handles a specific type of claim and applies
    rule-based verification against repository evidence.
    """

    verifier_name: str = "base"
    supported_claim_types: List[str] = []

    def can_verify(self, claim: Claim) -> bool:
        """Check if this verifier can handle the given claim type."""
        return claim.claim_type in self.supported_claim_types

    @abstractmethod
    def verify(
        self,
        claim: Claim,
        evidence: List[Evidence],
        repository_path: str,
    ) -> VerificationResult:
        """
        Verify a claim using evidence and repository content.

        Returns a VerificationResult with status:
        - supported: Evidence confirms the claim
        - contradicted: Evidence contradicts the claim
        - insufficient: Not enough evidence to decide
        - uncertain: Conflicting evidence
        """
        pass

    def _read_file_safely(self, file_path: Path) -> str:
        """Read a file safely."""
        try:
            return file_path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return ""

    def _find_evidence_by_relation(
        self,
        evidence: List[Evidence],
        relation: str,
    ) -> List[Evidence]:
        """Filter evidence by relation type."""
        return [e for e in evidence if e.relation == relation]
