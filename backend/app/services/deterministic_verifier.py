"""
Deterministic Verification Orchestrator.

Runs the appropriate verifier for each claim and aggregates results.
Phase 3, Step 17.
"""

from typing import List

from app.models.claim import Claim
from app.models.evidence import Evidence
from app.models.verification import VerificationPlan, VerificationResult

from app.verifiers.base_verifier import BaseVerifier
from app.verifiers.secret_verifier import SecretVerifier
from app.verifiers.authentication_verifier import AuthenticationVerifier
from app.verifiers.testing_verifier import TestingVerifier
from app.verifiers.structure_verifier import StructureVerifier
from app.verifiers.dependency_verifier import DependencyVerifier


# All registered verifiers
VERIFIERS: List[BaseVerifier] = [
    SecretVerifier(),
    AuthenticationVerifier(),
    TestingVerifier(),
    StructureVerifier(),
    DependencyVerifier(),
]


def _find_verifier(claim: Claim) -> BaseVerifier | None:
    """Find the appropriate verifier for a claim."""
    for verifier in VERIFIERS:
        if verifier.can_verify(claim):
            return verifier
    return None


def verify_claim(
    claim: Claim,
    evidence: List[Evidence],
    repository_path: str,
) -> VerificationResult:
    """
    Verify a single claim using deterministic verification.

    Finds the appropriate verifier and runs it against the evidence.
    """
    verifier = _find_verifier(claim)

    if verifier is None:
        return VerificationResult(
            claim_id=claim.claim_id,
            status="insufficient",
            rules_executed=["no_applicable_verifier"],
            supporting_evidence=[],
            contradicting_evidence=[],
        )

    # Filter evidence for this claim
    claim_evidence = [e for e in evidence if e.claim_id == claim.claim_id]

    return verifier.verify(claim, claim_evidence, repository_path)


def verify_all_claims(
    claims: List[Claim],
    evidence: List[Evidence],
    repository_path: str,
) -> List[VerificationResult]:
    """
    Verify all claims using deterministic verification.
    """
    results = []

    for claim in claims:
        if not claim.verification_required:
            continue

        result = verify_claim(claim, evidence, repository_path)
        results.append(result)

    supported = sum(1 for r in results if r.status == "supported")
    contradicted = sum(1 for r in results if r.status == "contradicted")
    uncertain = sum(1 for r in results if r.status == "uncertain")
    insufficient = sum(1 for r in results if r.status == "insufficient")

    print(f"  [DeterministicVerifier] Verified {len(results)} claims:")
    print(f"    Supported: {supported}")
    print(f"    Contradicted: {contradicted}")
    print(f"    Uncertain: {uncertain}")
    print(f"    Insufficient: {insufficient}")

    return results
