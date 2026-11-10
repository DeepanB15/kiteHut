"""
Truth Classifier for RepoLens Verification Engine.

Synthesizes multiple claim verdicts into an authoritative TruthStatus classification.
"""

from typing import List
from app.verification.models.truth import TruthStatus, VerificationVerdict


class TruthClassifier:
    """Classifies finding truth status from aggregated claim verdicts."""

    def classify(self, verdicts: List[VerificationVerdict]) -> TruthStatus:
        """Derive overall TruthStatus from individual claim verdicts."""
        if not verdicts:
            return TruthStatus.UNCERTAIN

        # If any essential claim is conclusively FALSE (debunked / refuted), the finding is FALSE
        if any(v.status == TruthStatus.FALSE for v in verdicts):
            return TruthStatus.FALSE

        statuses = [v.status for v in verdicts]

        # If all claims are TRUE -> TRUE
        if all(s == TruthStatus.TRUE for s in statuses):
            return TruthStatus.TRUE

        # If there is at least one TRUE claim and some PARTIALLY_TRUE/UNCERTAIN -> PARTIALLY_TRUE
        if any(s == TruthStatus.TRUE for s in statuses) or any(s == TruthStatus.PARTIALLY_TRUE for s in statuses):
            return TruthStatus.PARTIALLY_TRUE

        return TruthStatus.UNCERTAIN
