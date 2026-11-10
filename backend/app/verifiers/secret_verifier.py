"""
Secret Verifier.

Verifies claims about hardcoded secrets in source code.
Phase 3, Step 17.
"""

import re
from pathlib import Path
from typing import List

from app.models.claim import Claim
from app.models.evidence import Evidence, SUPPORTS, CONTRADICTS, NEUTRAL
from app.models.verification import VerificationResult
from app.verifiers.base_verifier import BaseVerifier


# Patterns that indicate a value is an environment variable reference
ENV_VAR_INDICATORS = [
    re.compile(r'os\.environ'),
    re.compile(r'os\.getenv'),
    re.compile(r'process\.env'),
    re.compile(r'\$\{[A-Z_]+\}'),
    re.compile(r'env\('),
]

# Patterns that indicate actual hardcoded secrets
SECRET_PATTERNS = [
    re.compile(r'["\'](?:AKIA|AGPA|AIDA|AROA|AIPA|ANPA|ANVA|ASIA)[A-Z0-9]{16}["\']'),  # AWS Access Key
    re.compile(r'["\']ghp_[A-Za-z0-9]{36}["\']'),  # GitHub PAT
    re.compile(r'["\']sk-[A-Za-z0-9]{32,}["\']'),  # OpenAI
    re.compile(r'["\']xox[bpsa]-[A-Za-z0-9-]+["\']'),  # Slack
    re.compile(r'(?:api_key|api_secret|secret_key|password|token)\s*=\s*["\'][^"\']{16,}["\']', re.I),
]


class SecretVerifier(BaseVerifier):
    """Verifier for hardcoded secret claims."""

    verifier_name = "secret_verifier"
    supported_claim_types = ["hardcoded_secret", "debug_mode_enabled", "insecure_configuration"]

    def verify(
        self,
        claim: Claim,
        evidence: List[Evidence],
        repository_path: str,
    ) -> VerificationResult:
        """Verify a hardcoded secret claim."""

        supporting = self._find_evidence_by_relation(evidence, SUPPORTS)
        contradicting = self._find_evidence_by_relation(evidence, CONTRADICTS)

        rules_executed = [
            "secret_pattern_scan",
            "environment_variable_check",
        ]

        # If we have direct contradicting evidence (env var usage)
        if contradicting and not supporting:
            return VerificationResult(
                claim_id=claim.claim_id,
                status="contradicted",
                rules_executed=rules_executed,
                supporting_evidence=[],
                contradicting_evidence=[e.evidence_id for e in contradicting],
            )

        # If we have direct supporting evidence (actual secrets found)
        if supporting:
            # Additional check: verify it's actually a hardcoded secret
            confirmed = []
            for ev in supporting:
                content = ev.content
                # Check it's not just a variable name
                if any(p.search(content) for p in SECRET_PATTERNS):
                    confirmed.append(ev)
                elif "=" in content:
                    # Has an assignment, likely hardcoded
                    confirmed.append(ev)

            if confirmed:
                return VerificationResult(
                    claim_id=claim.claim_id,
                    status="supported",
                    rules_executed=rules_executed,
                    supporting_evidence=[e.evidence_id for e in confirmed],
                    contradicting_evidence=[e.evidence_id for e in contradicting],
                )

        # If we have both supporting and contradicting
        if supporting and contradicting:
            return VerificationResult(
                claim_id=claim.claim_id,
                status="uncertain",
                rules_executed=rules_executed,
                supporting_evidence=[e.evidence_id for e in supporting],
                contradicting_evidence=[e.evidence_id for e in contradicting],
            )

        # No evidence found
        return VerificationResult(
            claim_id=claim.claim_id,
            status="insufficient",
            rules_executed=rules_executed,
            supporting_evidence=[],
            contradicting_evidence=[],
        )
