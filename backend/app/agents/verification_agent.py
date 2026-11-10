"""
Verification Agent.

Optional AI-powered verification for claims that cannot be
resolved deterministically.
Phase 3, Step 17 (optional AI verification).
"""

from typing import List

from app.agents.base_agent import BaseAgent
from app.models.claim import Claim
from app.models.evidence import Evidence
from app.prompts.verification_prompt import (
    VERIFICATION_SYSTEM_PROMPT,
    build_verification_prompt,
)


class VerificationResult:
    """Simple result from AI verification."""

    def __init__(
        self,
        truth_value: str,
        confidence: float,
        reasoning: str,
    ):
        self.truth_value = truth_value
        self.confidence = confidence
        self.reasoning = reasoning


class VerificationAgent(BaseAgent):
    """
    AI-powered verification agent for uncertain claims.

    Only used when deterministic verification is insufficient.
    """

    def verify_claim(
        self,
        claim: Claim,
        evidence: List[Evidence],
        repository_path: str,
    ) -> VerificationResult | None:
        """
        Verify a claim using the LLM.

        Returns a VerificationResult or None if LLM is unavailable.
        """
        print(f"  [VerificationAgent] Verifying claim: {claim.claim_id}")

        if not self.llm.is_available():
            print("  [VerificationAgent] LLM not available, returning UNCERTAIN.")
            return VerificationResult(
                truth_value="UNCERTAIN",
                confidence=30.0,
                reasoning="LLM not available for verification.",
            )

        # Prepare evidence for prompt
        claim_evidence = [
            {
                "source": e.source,
                "file_path": e.file_path,
                "content": e.content,
                "relation": e.relation,
            }
            for e in evidence
            if e.claim_id == claim.claim_id
        ]

        # Build prompt
        prompt = build_verification_prompt(
            claim_statement=claim.statement,
            claim_type=claim.claim_type,
            evidence_items=claim_evidence,
            relevant_files=claim.target_files,
        )

        try:
            response = self._call_llm(prompt, VERIFICATION_SYSTEM_PROMPT)
            parsed = self._parse_json_response(response)

            truth_value = parsed.get("truth_value", "UNCERTAIN")
            confidence = float(parsed.get("confidence", 50))
            reasoning = parsed.get("reasoning", "No reasoning provided.")

            # Clamp confidence
            confidence = max(0.0, min(100.0, confidence))

            # Validate truth value
            valid_truth = {"TRUE", "LIKELY_TRUE", "UNCERTAIN", "LIKELY_FALSE", "FALSE"}
            if truth_value not in valid_truth:
                truth_value = "UNCERTAIN"

            return VerificationResult(
                truth_value=truth_value,
                confidence=confidence,
                reasoning=reasoning,
            )

        except Exception as e:
            print(f"  [VerificationAgent] Error: {e}")
            return VerificationResult(
                truth_value="UNCERTAIN",
                confidence=20.0,
                reasoning=f"Verification failed: {str(e)}",
            )
