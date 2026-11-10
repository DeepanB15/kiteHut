"""
Confidence Engine for RepoLens Verification Engine.

Computes a deterministic confidence score (0.0-100.0) based on verdict strength,
evidence coverage, and truth classification.
"""

from typing import List
from app.verification.models.evidence import EvidenceItem
from app.verification.models.truth import TruthStatus, VerificationVerdict


class ConfidenceEngine:
    """Computes explainable verification confidence scores."""

    def compute_confidence(
        self,
        truth_status: TruthStatus,
        verdicts: List[VerificationVerdict],
        evidence_items: List[EvidenceItem],
    ) -> float:
        """Compute aggregate confidence percentage."""
        if not verdicts:
            return 20.0

        if truth_status == TruthStatus.FALSE:
            # High confidence in the falseness/refutation if backed by contradictory evidence
            avg_v_conf = sum(v.confidence for v in verdicts) / len(verdicts)
            return round(avg_v_conf, 1)

        # Base confidence is the average confidence of all verdicts
        avg_v_conf = sum(v.confidence for v in verdicts) / len(verdicts)

        # Bonus for corroborating evidence count
        corrob_count = sum(1 for e in evidence_items if e.is_corroborating)
        evidence_bonus = min(15.0, corrob_count * 3.0)

        # Truth status multiplier
        multipliers = {
            TruthStatus.TRUE: 1.0,
            TruthStatus.PARTIALLY_TRUE: 0.75,
            TruthStatus.UNCERTAIN: 0.40,
            TruthStatus.FALSE: 1.0,
        }

        raw_score = (avg_v_conf + evidence_bonus) * multipliers.get(truth_status, 0.5)
        return min(100.0, max(0.0, round(raw_score, 1)))
