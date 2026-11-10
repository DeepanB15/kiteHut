"""
Truth Engine.

Converts evidence and verification results into truth classifications.
Phase 3, Step 19.
"""

from typing import List

from app.models.claim import Claim
from app.models.evidence import Evidence, SUPPORTS, CONTRADICTS
from app.models.verification import VerificationResult
from app.models.verified_finding import VerifiedFinding


# ============================================================
# Truth classification logic
# ============================================================

def classify_truth(
    claim: Claim,
    verification_result: VerificationResult,
    evidence: List[Evidence],
) -> str:
    """
    Classify the truth value of a claim based on evidence.

    Truth States:
    - TRUE: Strong direct evidence + no meaningful contradiction
    - LIKELY_TRUE: Multiple supporting evidence + some uncertainty
    - UNCERTAIN: Insufficient evidence OR conflicting evidence
    - LIKELY_FALSE: Weak support + strong contradiction
    - FALSE: Claim directly contradicted by repository evidence
    """
    supporting = [
        e for e in evidence
        if e.claim_id == claim.claim_id and e.relation == SUPPORTS
    ]
    contradicting = [
        e for e in evidence
        if e.claim_id == claim.claim_id and e.relation == CONTRADICTS
    ]

    strong_support = [e for e in supporting if e.strength == "strong"]
    strong_contradict = [e for e in contradicting if e.strength == "strong"]

    status = verification_result.status

    # Decision logic based on verification status and evidence

    # If verification status is "contradicted" -> FALSE
    if status == "contradicted":
        if len(strong_contradict) >= 2:
            return "FALSE"
        elif contradicting:
            return "LIKELY_FALSE"
        return "UNCERTAIN"

    # If verification status is "supported"
    if status == "supported":
        if strong_support and not contradicting:
            return "TRUE"
        elif supporting and not contradicting:
            return "LIKELY_TRUE"
        elif supporting and contradicting:
            return "UNCERTAIN"
        return "LIKELY_TRUE"

    # If verification status is "uncertain"
    if status == "uncertain":
        return "UNCERTAIN"

    # If verification status is "insufficient"
    if status == "insufficient":
        if strong_support:
            return "LIKELY_TRUE"
        elif supporting and not contradicting:
            return "LIKELY_TRUE"
        elif contradicting:
            return "LIKELY_FALSE"
        return "UNCERTAIN"

    return "UNCERTAIN"


def generate_truth_summary(
    claim: Claim,
    truth_value: str,
    verification_result: VerificationResult,
    evidence: List[Evidence],
) -> str:
    """Generate a human-readable verification summary."""
    supporting = [
        e for e in evidence
        if e.claim_id == claim.claim_id and e.relation == SUPPORTS
    ]
    contradicting = [
        e for e in evidence
        if e.claim_id == claim.claim_id and e.relation == CONTRADICTS
    ]

    parts = []
    parts.append(f"Claim: {claim.statement}")
    parts.append(f"Truth Value: {truth_value}")
    parts.append(f"Verification: {verification_result.status}")

    if supporting:
        parts.append(f"Supporting evidence: {len(supporting)} items")
        for ev in supporting[:3]:
            parts.append(f"  - [{ev.source}] {ev.file_path}: {ev.content[:80]}")

    if contradicting:
        parts.append(f"Contradicting evidence: {len(contradicting)} items")
        for ev in contradicting[:3]:
            parts.append(f"  - [{ev.source}] {ev.file_path}: {ev.content[:80]}")

    if verification_result.rules_executed:
        parts.append(f"Rules: {', '.join(verification_result.rules_executed)}")

    return "\n".join(parts)
