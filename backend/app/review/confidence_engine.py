"""
Phase 6 — Confidence Engine.
Confidence derived from verification + evidence quality, NOT severity.
"""
from .verification_status import VerificationStatus
from .evidence_quality import EvidenceQuality

class ConfidenceLevel(str):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

class ConfidenceEngine:
    def compute(self, status: VerificationStatus, quality: EvidenceQuality) -> str:
        if status == VerificationStatus.VERIFIED and quality == EvidenceQuality.STRONG:
            return ConfidenceLevel.HIGH
        if status == VerificationStatus.VERIFIED and quality == EvidenceQuality.MEDIUM:
            return ConfidenceLevel.MEDIUM
        if status == VerificationStatus.VERIFIED and quality == EvidenceQuality.WEAK:
            return ConfidenceLevel.LOW
        if status == VerificationStatus.INCONCLUSIVE:
            return ConfidenceLevel.LOW
        if status == VerificationStatus.STALE:
            return ConfidenceLevel.LOW
        if status == VerificationStatus.UNSUPPORTED:
            return ConfidenceLevel.LOW
        return ConfidenceLevel.LOW
