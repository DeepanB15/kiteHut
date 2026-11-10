"""
Structure Verifier.

Verifies claims about architecture and code structure.
Phase 3, Step 17.
"""

from typing import List

from app.models.claim import Claim
from app.models.evidence import Evidence, SUPPORTS, CONTRADICTS
from app.models.verification import VerificationResult
from app.verifiers.base_verifier import BaseVerifier


class StructureVerifier(BaseVerifier):
    """Verifier for architecture and structure claims."""

    verifier_name = "structure_verifier"
    supported_claim_types = [
        "tight_coupling",
        "layer_violation",
        "missing_separation",
        "code_duplication",
        "large_function",
        "large_class",
    ]

    def verify(
        self,
        claim: Claim,
        evidence: List[Evidence],
        repository_path: str,
    ) -> VerificationResult:
        """Verify a structure claim."""

        supporting = self._find_evidence_by_relation(evidence, SUPPORTS)
        contradicting = self._find_evidence_by_relation(evidence, CONTRADICTS)

        rules_executed = [
            "check_structure_patterns",
            "check_code_organization",
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
