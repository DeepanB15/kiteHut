"""
Phase 6 — Evidence Verification Status.
Explicit verification states for review findings.
"""
from enum import Enum

class VerificationStatus(str, Enum):
    VERIFIED = "verified"
    UNSUPPORTED = "unsupported"
    STALE = "stale"
    INCONCLUSIVE = "inconclusive"
