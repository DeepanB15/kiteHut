"""
Phase 6 — Evidence Quality Assessment.
Deterministic quality levels for review findings.
"""
from enum import Enum

class EvidenceQuality(str, Enum):
    STRONG = "strong"
    MEDIUM = "medium"
    WEAK = "weak"
