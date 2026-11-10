"""
Dependency Verifier.

Verifies claims about dependencies and packages.
Phase 3, Step 17.
"""

from typing import List

from app.models.claim import Claim
from app.models.evidence import Evidence, SUPPORTS, CONTRADICTS
from app.models.verification import VerificationResult
from app.verifiers.base_verifier import BaseVerifier


class DependencyVerifier(BaseVerifier):
    """Verifier for dependency-related claims."""

    verifier_name = "dependency_verifier"
    supported_claim_types = [
        "missing_test_framework",
    ]

    def verify(
        self,
        claim: Claim,
        evidence: List[Evidence],
        repository_path: str,
    ) -> VerificationResult:
        """Verify a dependency claim."""

        supporting = self._find_evidence_by_relation(evidence, SUPPORTS)
        contradicting = self._find_evidence_by_relation(evidence, CONTRADICTS)

        rules_executed = [
            "check_dependency_files",
            "check_test_framework_deps",
        ]

        if contradicting and not supporting:
            return VerificationResult(
                claim_id=claim.claim_id,
                status="contradicted",
                rules_executed=rules_executed,
                supporting_evidence=[],
                contradicting_evidence=[e.evidence_id for e in contradicting],
            )

        if supporting and not contradicting:
            return VerificationResult(
                claim_id=claim.claim_id,
                status="supported",
                rules_executed=rules_executed,
                supporting_evidence=[e.evidence_id for e in supporting],
                contradicting_evidence=[],
            )

        if supporting and contradicting:
            return VerificationResult(
                claim_id=claim.claim_id,
                status="uncertain",
                rules_executed=rules_executed,
                supporting_evidence=[e.evidence_id for e in supporting],
                contradicting_evidence=[e.evidence_id for e in contradicting],
            )

        return VerificationResult(
            claim_id=claim.claim_id,
            status="insufficient",
            rules_executed=rules_executed,
            supporting_evidence=[],
            contradicting_evidence=[],
        )
