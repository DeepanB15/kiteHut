"""
Confidence Engine.

Calculates confidence scores for verified findings.
Phase 3, Step 19.
"""

from typing import List

from app.models.claim import Claim
from app.models.evidence import Evidence, SUPPORTS, CONTRADICTS
from app.models.verification import VerificationResult


# ============================================================
# Confidence weights
# ============================================================

# Direct evidence weight (highest)
DIRECT_EVIDENCE_WEIGHT = 40

# Deterministic verification weight
VERIFICATION_WEIGHT = 30

# Evidence consistency weight
CONSISTENCY_WEIGHT = 15

# Cross-agent support weight
CROSS_AGENT_WEIGHT = 10

# AI confidence weight (lowest - protects against hallucination)
AI_CONFIDENCE_WEIGHT = 5


def calculate_confidence(
    claim: Claim,
    verification_result: VerificationResult,
    evidence: List[Evidence],
    cross_agent_support: bool = False,
) -> float:
    """
    Calculate a confidence score (0-100) for a verified finding.

    Formula:
    Confidence = Evidence Score + Verification Score + Consistency Score
              + Cross-Agent Score - Contradiction Penalty

    Weights:
    - Direct Evidence: 40%
    - Deterministic Verification: 30%
    - Evidence Consistency: 15%
    - Cross-Agent Support: 10%
    - AI Confidence: 5% (lowest)
    """
    claim_evidence = [
        e for e in evidence if e.claim_id == claim.claim_id
    ]
    supporting = [e for e in claim_evidence if e.relation == SUPPORTS]
    contradicting = [e for e in claim_evidence if e.relation == CONTRADICTS]

    # 1. Direct Evidence Score (0-40)
    evidence_score = 0.0
    if supporting:
        strong_support = [e for e in supporting if e.strength == "strong"]
        medium_support = [e for e in supporting if e.strength == "medium"]

        if strong_support:
            evidence_score = DIRECT_EVIDENCE_WEIGHT * min(1.0, len(strong_support) * 0.5)
        elif medium_support:
            evidence_score = DIRECT_EVIDENCE_WEIGHT * 0.5 * min(1.0, len(medium_support) * 0.33)
        else:
            evidence_score = DIRECT_EVIDENCE_WEIGHT * 0.2

    # 2. Verification Score (0-30)
    verification_score = 0.0
    if verification_result.status == "supported":
        verification_score = VERIFICATION_WEIGHT
    elif verification_result.status == "contradicted":
        verification_score = 0.0
    elif verification_result.status == "uncertain":
        verification_score = VERIFICATION_WEIGHT * 0.3
    elif verification_result.status == "insufficient":
        verification_score = VERIFICATION_WEIGHT * 0.1

    # 3. Consistency Score (0-15)
    # Based on whether evidence is consistent (all supporting or all contradicting)
    consistency_score = 0.0
    if supporting and not contradicting:
        consistency_score = CONSISTENCY_WEIGHT
    elif contradicting and not supporting:
        consistency_score = 0.0
    elif supporting and contradicting:
        # Mixed evidence reduces consistency
        ratio = len(supporting) / (len(supporting) + len(contradicting))
        consistency_score = CONSISTENCY_WEIGHT * ratio
    else:
        # No evidence
        consistency_score = CONSISTENCY_WEIGHT * 0.2

    # 4. Cross-Agent Score (0-10)
    cross_agent_score = CROSS_AGENT_WEIGHT if cross_agent_support else 0.0

    # 5. AI Confidence (0-5) - always low
    # Since we don't use AI verification in deterministic path, give baseline
    ai_score = 2.5

    # 6. Contradiction Penalty
    contradiction_penalty = 0.0
    if contradicting:
        strong_contradict = [
            e for e in contradicting if e.strength == "strong"
        ]
        if strong_contradict:
            contradiction_penalty = 10.0 * min(1.0, len(strong_contradict) * 0.5)
        else:
            contradiction_penalty = 5.0 * min(1.0, len(contradicting) * 0.33)

    # Calculate total
    total = (
        evidence_score
        + verification_score
        + consistency_score
        + cross_agent_score
        + ai_score
        - contradiction_penalty
    )

    # Clamp to 0-100
    return max(0.0, min(100.0, total))
