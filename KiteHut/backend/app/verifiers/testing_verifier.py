"""
Testing Verifier.

Verifies claims about missing tests or testing issues.
Phase 3, Step 17.
"""

from pathlib import Path
from typing import List

from app.models.claim import Claim
from app.models.evidence import Evidence, SUPPORTS, CONTRADICTS
from app.models.verification import VerificationResult
from app.verifiers.base_verifier import BaseVerifier


class TestingVerifier(BaseVerifier):
    """Verifier for testing-related claims."""

    verifier_name = "testing_verifier"
    supported_claim_types = [
        "missing_tests",
        "low_test_coverage",
        "missing_integration_tests",
        "missing_test_framework",
    ]

    def verify(
        self,
        claim: Claim,
        evidence: List[Evidence],
        repository_path: str,
    ) -> VerificationResult:
        """Verify a testing claim."""

        supporting = self._find_evidence_by_relation(evidence, SUPPORTS)
        contradicting = self._find_evidence_by_relation(evidence, CONTRADICTS)

        rules_executed = [
            "check_test_directories",
            "check_test_files",
            "check_test_to_source_ratio",
        ]

        # Contradicting evidence means tests DO exist
        if contradicting:
            strong = [e for e in contradicting if e.strength == "strong"]
            if len(strong) >= 1 or len(contradicting) >= 2:
                return VerificationResult(
                    claim_id=claim.claim_id,
                    status="contradicted",
                    rules_executed=rules_executed,
                    supporting_evidence=[e.evidence_id for e in supporting],
                    contradicting_evidence=[e.evidence_id for e in contradicting],
                )
            else:
                return VerificationResult(
                    claim_id=claim.claim_id,
                    status="uncertain",
                    rules_executed=rules_executed,
                    supporting_evidence=[e.evidence_id for e in supporting],
                    contradicting_evidence=[e.evidence_id for e in contradicting],
                )

        if supporting:
            return VerificationResult(
                claim_id=claim.claim_id,
                status="supported",
                rules_executed=rules_executed,
                supporting_evidence=[e.evidence_id for e in supporting],
                contradicting_evidence=[],
            )

        return VerificationResult(
            claim_id=claim.claim_id,
            status="insufficient",
            rules_executed=rules_executed,
            supporting_evidence=[],
            contradicting_evidence=[],
        )
