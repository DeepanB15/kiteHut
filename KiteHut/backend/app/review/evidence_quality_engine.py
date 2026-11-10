"""
Phase 6 — Evidence Quality Assessment.
Objective quality scoring based on verification signals.
"""
from .verification_status import VerificationStatus
from .evidence_quality import EvidenceQuality


class EvidenceQualityEngine:
    def assess(self, status: VerificationStatus, snippet_match: bool,
               has_snippet: bool, has_context: bool) -> EvidenceQuality:
        if status == VerificationStatus.VERIFIED and snippet_match and has_snippet:
            return EvidenceQuality.STRONG
        if status == VerificationStatus.VERIFIED and snippet_match:
            return EvidenceQuality.MEDIUM
        if status == VerificationStatus.VERIFIED and not snippet_match:
            return EvidenceQuality.WEAK
        if status == VerificationStatus.INCONCLUSIVE:
            return EvidenceQuality.WEAK
        if status == VerificationStatus.STALE:
            return EvidenceQuality.WEAK
        if status == VerificationStatus.UNSUPPORTED:
            return EvidenceQuality.WEAK
        return EvidenceQuality.WEAK
