"""
Base Verifier Interface for RepoLens Verification Engine.
"""

from abc import ABC, abstractmethod
from typing import List, Optional
from app.verification.models.claim import ExtractedClaim
from app.verification.models.evidence import EvidenceItem
from app.verification.models.truth import TruthStatus, VerificationVerdict


class BaseVerifier(ABC):
    """Abstract base class for deterministic domain verifiers."""

    name: str = "base_verifier"

    @abstractmethod
    def verify(
        self,
        claim: ExtractedClaim,
        evidence: List[EvidenceItem],
    ) -> VerificationVerdict:
        """Verify claim against collected evidence items."""
        pass
