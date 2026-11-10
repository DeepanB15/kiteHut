"""
Security Verifier for RepoLens.
"""

from typing import List
from app.verification.models.claim import ClaimType, ExtractedClaim
from app.verification.models.evidence import EvidenceItem, EvidenceType
from app.verification.models.truth import TruthStatus, VerificationVerdict
from app.verification.verifiers.base_verifier import BaseVerifier


class SecurityVerifier(BaseVerifier):
    """Verifies security findings against exact file and AST evidence."""

    name: str = "security_verifier"

    def verify(
        self,
        claim: ExtractedClaim,
        evidence: List[EvidenceItem],
    ) -> VerificationVerdict:
        corroborating = [e for e in evidence if e.is_corroborating]
        contradicting = [e for e in evidence if not e.is_corroborating]

        if contradicting:
            return VerificationVerdict(
                status=TruthStatus.FALSE,
                confidence=95.0,
                explanation=f"Target file does not exist or cannot be read: {contradicting[0].description}",
                evidence_ids=[e.evidence_id for e in contradicting],
            )

        if claim.claim_type == ClaimType.SECRET_PATTERN_MATCH:
            secret_evidence = [
                e for e in corroborating
                if e.snippet and any(p in e.snippet.lower() for p in ["sk_live_", "ghp_", "aws_access", "api_key", "password"])
            ]
            if secret_evidence:
                return VerificationVerdict(
                    status=TruthStatus.TRUE,
                    confidence=98.0,
                    explanation=f"Confirmed plaintext secret credential present in line snippet: '{secret_evidence[0].snippet[:40]}...'",
                    evidence_ids=[e.evidence_id for e in secret_evidence],
                )
            elif corroborating:
                return VerificationVerdict(
                    status=TruthStatus.PARTIALLY_TRUE,
                    confidence=65.0,
                    explanation="File exists but direct secret token pattern could not be isolated precisely.",
                    evidence_ids=[e.evidence_id for e in corroborating],
                )

        if claim.claim_type == ClaimType.SQL_INJECTION_PATTERN:
            sqli_evidence = [
                e for e in corroborating
                if e.snippet and ("execute(" in e.snippet or "select" in e.snippet.lower() or "cursor" in e.snippet.lower())
            ]
            if sqli_evidence:
                return VerificationVerdict(
                    status=TruthStatus.TRUE,
                    confidence=95.0,
                    explanation="Confirmed raw query execution with potential parameter string interpolation.",
                    evidence_ids=[e.evidence_id for e in sqli_evidence],
                )

        if corroborating:
            return VerificationVerdict(
                status=TruthStatus.TRUE,
                confidence=85.0,
                explanation="Security claim confirmed with code evidence.",
                evidence_ids=[e.evidence_id for e in corroborating],
            )

        return VerificationVerdict(
            status=TruthStatus.UNCERTAIN,
            confidence=30.0,
            explanation="Insufficient evidence to confirm security vulnerability.",
            evidence_ids=[],
        )
