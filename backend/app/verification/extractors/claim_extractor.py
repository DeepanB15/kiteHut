"""
Claim Extractor for RepoLens Trust & Verification Engine.

Deconstructs raw findings and agent claims into atomic, verifiable propositions.
"""

import re
from typing import List, Optional
from app.intelligence.models.findings import Finding, FindingCategory
from app.verification.models.claim import ClaimType, ExtractedClaim


class ClaimExtractor:
    """Extracts falsifiable propositions from findings."""

    def extract_claims(self, finding: Finding) -> List[ExtractedClaim]:
        """Extract atomic claims from a specialist finding."""
        claims: List[ExtractedClaim] = []

        # 1. Base claim: Target file exists
        if finding.file_path:
            claims.append(
                ExtractedClaim(
                    claim_type=ClaimType.FILE_EXISTS,
                    statement=f"Target file '{finding.file_path}' exists in the repository.",
                    target_file=finding.file_path,
                    target_line=finding.line_number,
                )
            )

        # 2. Category-specific claims
        if finding.category == FindingCategory.SECURITY:
            claims.extend(self._extract_security_claims(finding))
        elif finding.category == FindingCategory.CONFIGURATION:
            claims.extend(self._extract_config_claims(finding))
        elif finding.category == FindingCategory.ARCHITECTURE:
            claims.extend(self._extract_architecture_claims(finding))
        elif finding.category == FindingCategory.TESTING:
            claims.extend(self._extract_testing_claims(finding))
        elif finding.category == FindingCategory.DEPENDENCY:
            claims.extend(self._extract_dependency_claims(finding))
        elif finding.category == FindingCategory.CODE_REVIEW:
            claims.extend(self._extract_code_review_claims(finding))
        elif finding.category == FindingCategory.QUALITY:
            claims.extend(self._extract_quality_claims(finding))

        # 3. Fallback generic claim if none extracted
        if not claims:
            claims.append(
                ExtractedClaim(
                    claim_type=ClaimType.GENERIC,
                    statement=finding.title,
                    target_file=finding.file_path,
                    target_line=finding.line_number,
                    expected_pattern=finding.code_snippet,
                )
            )

        return claims

    def _extract_security_claims(self, finding: Finding) -> List[ExtractedClaim]:
        claims: List[ExtractedClaim] = []
        text = f"{finding.title} {finding.description} {finding.evidence or ''}".lower()

        if "secret" in text or "credential" in text or "key" in text or "password" in text:
            claims.append(
                ExtractedClaim(
                    claim_type=ClaimType.SECRET_PATTERN_MATCH,
                    statement=f"Hardcoded sensitive secret found in '{finding.file_path}'.",
                    target_file=finding.file_path,
                    target_line=finding.line_number,
                    expected_pattern=finding.code_snippet,
                )
            )

        if "sql injection" in text or "query" in text:
            claims.append(
                ExtractedClaim(
                    claim_type=ClaimType.SQL_INJECTION_PATTERN,
                    statement=f"Dynamic string-interpolated SQL query in '{finding.file_path}'.",
                    target_file=finding.file_path,
                    target_line=finding.line_number,
                    expected_pattern=finding.code_snippet,
                )
            )

        return claims

    def _extract_config_claims(self, finding: Finding) -> List[ExtractedClaim]:
        claims: List[ExtractedClaim] = []
        # Check for env var names in title/description (e.g. STRIPE_API_SECRET)
        match = re.search(r"['\"]?([A-Z0-9_]{3,})['\"]?", finding.title + " " + finding.description)
        env_key = match.group(1) if match else None

        claims.append(
            ExtractedClaim(
                claim_type=ClaimType.CONFIG_KEY_MISSING,
                statement=f"Environment variable '{env_key or 'unknown'}' missing from .env.example.",
                target_file=finding.file_path,
                target_line=finding.line_number,
                context_data={"env_key": env_key} if env_key else {},
            )
        )
        return claims

    def _extract_architecture_claims(self, finding: Finding) -> List[ExtractedClaim]:
        claims: List[ExtractedClaim] = []
        text = f"{finding.title} {finding.description}".lower()

        if "circular" in text:
            claims.append(
                ExtractedClaim(
                    claim_type=ClaimType.CIRCULAR_IMPORT,
                    statement=f"Circular import loop involving '{finding.file_path}'.",
                    target_file=finding.file_path,
                    target_line=finding.line_number,
                    context_data={"evidence": finding.evidence},
                )
            )
        return claims

    def _extract_testing_claims(self, finding: Finding) -> List[ExtractedClaim]:
        claims: List[ExtractedClaim] = []
        claims.append(
            ExtractedClaim(
                claim_type=ClaimType.UNTESTED_MODULE,
                statement=f"Target module '{finding.file_path}' lacks comprehensive unit/integration tests.",
                target_file=finding.file_path,
                target_line=finding.line_number,
            )
        )
        return claims

    def _extract_dependency_claims(self, finding: Finding) -> List[ExtractedClaim]:
        claims: List[ExtractedClaim] = []
        claims.append(
            ExtractedClaim(
                claim_type=ClaimType.UNPINNED_DEPENDENCY,
                statement=f"Unpinned dependency in '{finding.file_path}'.",
                target_file=finding.file_path,
                target_line=finding.line_number,
            )
        )
        return claims

    def _extract_code_review_claims(self, finding: Finding) -> List[ExtractedClaim]:
        claims: List[ExtractedClaim] = []
        claims.append(
            ExtractedClaim(
                claim_type=ClaimType.GIT_DIFF_CONTAINS,
                statement=f"Git diff in '{finding.file_path}' contains debugging or review artifact.",
                target_file=finding.file_path,
                target_line=finding.line_number,
                expected_pattern=finding.code_snippet,
            )
        )
        return claims

    def _extract_quality_claims(self, finding: Finding) -> List[ExtractedClaim]:
        claims: List[ExtractedClaim] = []
        claims.append(
            ExtractedClaim(
                claim_type=ClaimType.HIGH_COMPLEXITY,
                statement=f"Code quality / high complexity in '{finding.file_path}'.",
                target_file=finding.file_path,
                target_line=finding.line_number,
            )
        )
        return claims
