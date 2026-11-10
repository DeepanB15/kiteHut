"""
Authentication Verifier.

Verifies claims about missing authentication/authorization.
Phase 3, Step 17.
"""

from pathlib import Path
from typing import List

from app.models.claim import Claim
from app.models.evidence import Evidence, SUPPORTS, CONTRADICTS
from app.models.verification import VerificationResult
from app.verifiers.base_verifier import BaseVerifier


class AuthenticationVerifier(BaseVerifier):
    """Verifier for authentication/authorization claims."""

    verifier_name = "authentication_verifier"
    supported_claim_types = [
        "missing_authentication",
        "missing_authorization",
    ]

    def verify(
        self,
        claim: Claim,
        evidence: List[Evidence],
        repository_path: str,
    ) -> VerificationResult:
        """Verify an authentication claim."""

        supporting = self._find_evidence_by_relation(evidence, SUPPORTS)
        contradicting = self._find_evidence_by_relation(evidence, CONTRADICTS)

        rules_executed = [
            "check_auth_dependencies",
            "check_middleware",
            "check_auth_modules",
        ]

        # Contradicting evidence means auth IS present
        if contradicting:
            # Check strength of contradicting evidence
            strong_contradictions = [
                e for e in contradicting if e.strength == "strong"
            ]

            if len(strong_contradictions) >= 2 or len(contradicting) >= 3:
                return VerificationResult(
                    claim_id=claim.claim_id,
                    status="contradicted",
                    rules_executed=rules_executed,
                    supporting_evidence=[e.evidence_id for e in supporting],
                    contradicting_evidence=[e.evidence_id for e in contradicting],
                )
            elif contradicting:
                return VerificationResult(
                    claim_id=claim.claim_id,
                    status="uncertain",
                    rules_executed=rules_executed,
                    supporting_evidence=[e.evidence_id for e in supporting],
                    contradicting_evidence=[e.evidence_id for e in contradicting],
                )

        # Only supporting evidence or no evidence
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
