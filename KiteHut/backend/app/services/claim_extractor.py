"""
Claim Extraction Engine.

Converts AI agent findings into structured, verifiable claims.
Phase 3, Step 13.
"""

import re
from typing import List

from app.models.claim import Claim, ALL_CLAIM_TYPES


def _generate_claim_id(index: int) -> str:
    """Generate a unique claim ID."""
    return f"claim_{index:04d}"


# ============================================================
# Claim type detection patterns
# ============================================================

# Maps regex patterns to (claim_type, category)
CLAIM_PATTERNS = [
    # Security patterns
    (
        re.compile(r"hardcoded|api.?key|secret|token|password|credential", re.I),
        "hardcoded_secret",
        "security_risk",
    ),
    (
        re.compile(r"no\s+(auth|authentication)|missing\s+auth|auth.*missing|without.*auth", re.I),
        "missing_authentication",
        "security_risk",
    ),
    (
        re.compile(r"no\s+(authorization|access.control)|missing.*authoriz", re.I),
        "missing_authorization",
        "security_risk",
    ),
    (
        re.compile(r"(input\s+validat|sanitiz|escape|injection)", re.I),
        "weak_input_validation",
        "security_risk",
    ),
    (
        re.compile(r"debug\s*mode|debug\s*=\s*true|DEBUG\s*=\s*True", re.I),
        "debug_mode_enabled",
        "security_risk",
    ),
    (
        re.compile(r"(insecure|unsafe|dangerous)\s+(config|setting|pattern)", re.I),
        "insecure_configuration",
        "security_risk",
    ),

    # Architecture patterns
    (
        re.compile(r"(tight.?coupl|highly.?coupl|circular.?dep|god.?class)", re.I),
        "tight_coupling",
        "architecture_issue",
    ),
    (
        re.compile(r"(layer.?viol|wrong.?layer|presentation.*business|route.*logic)", re.I),
        "layer_violation",
        "architecture_issue",
    ),
    (
        re.compile(r"(missing.*separ|lack.*separ|no.*boundar)", re.I),
        "missing_separation",
        "architecture_issue",
    ),

    # Quality patterns
    (
        re.compile(r"(duplicat|copy.?paste|repeated.?code|similar.?function)", re.I),
        "code_duplication",
        "quality_issue",
    ),
    (
        re.compile(r"(large.?function|long.?function|too.?long|excessive.?length)", re.I),
        "large_function",
        "quality_issue",
    ),
    (
        re.compile(r"(large.?class|god.?class|too.?many.?responsibilit)", re.I),
        "large_class",
        "quality_issue",
    ),
    (
        re.compile(r"(error.?handl|exception.?handl|no.?try.?catch|bare.?except|missing.*catch)", re.I),
        "poor_error_handling",
        "quality_issue",
    ),

    # Testing patterns
    (
        re.compile(r"(no\s+test|missing\s+test|without\s+test|test.*missing|lack.*test)", re.I),
        "missing_tests",
        "testing_issue",
    ),
    (
        re.compile(r"(low\s+coverage|poor\s+coverage|insufficient\s+coverage)", re.I),
        "low_test_coverage",
        "testing_issue",
    ),
    (
        re.compile(r"(no\s+integration.?test|missing\s+integration|lack\s+integration)", re.I),
        "missing_integration_tests",
        "testing_issue",
    ),
    (
        re.compile(r"(no\s+test.?framework|missing.*framework|no.*jest|no.*pytest|no.*junit)", re.I),
        "missing_test_framework",
        "testing_issue",
    ),
]


def _detect_claim_type(finding_text: str) -> tuple[str, str]:
    """
    Detect claim type from finding text using pattern matching.
    Returns (claim_type, category) or defaults.
    """
    for pattern, claim_type, category in CLAIM_PATTERNS:
        if pattern.search(finding_text):
            return claim_type, category
    return "unknown", "unknown"


def _extract_target_files(finding_text: str) -> List[str]:
    """Extract file references from finding text."""
    files = []

    # Match common file paths
    patterns = [
        r'`([^`]+\.\w{1,5})`',  # Backtick-wrapped filenames
        r'(\w+/\w+\.\w{1,5})',  # path/to/file.ext
        r'(\w+\.\w{1,5})\s',    # file.ext followed by space
    ]

    for pattern in patterns:
        matches = re.findall(pattern, finding_text)
        for match in matches:
            if match not in files and len(match) > 3:
                files.append(match)

    return files[:5]  # Limit to 5 files


def extract_claims_from_findings(
    findings: List[dict],
    source_agent: str,
    start_index: int = 1,
) -> List[Claim]:
    """
    Extract structured claims from AI agent findings.

    Args:
        findings: List of finding dicts with 'statement' key
        source_agent: Name of the source agent
        start_index: Starting index for claim IDs

    Returns:
        List of Claim objects
    """
    claims = []

    for i, finding in enumerate(findings):
        statement = finding.get("statement", "")

        if not statement or len(statement.strip()) < 10:
            continue

        claim_type, category = _detect_claim_type(statement)
        target_files = _extract_target_files(statement)

        claim = Claim(
            claim_id=_generate_claim_id(start_index + i),
            source_agent=source_agent,
            claim_type=claim_type,
            category=category,
            statement=statement,
            target_files=target_files,
            candidate_evidence=[statement],
            verification_required=True,
        )

        claims.append(claim)

    return claims


def extract_all_claims(
    architecture_result=None,
    security_result=None,
    quality_result=None,
    testing_result=None,
) -> List[Claim]:
    """
    Extract claims from all agent results.

    Collects findings from every Phase 2 agent and converts them
    into structured Claim objects.
    """
    all_claims = []
    claim_index = 1

    # Security agent findings
    if security_result:
        # Potential risks
        findings = [
            {"statement": risk}
            for risk in security_result.potential_risks
        ]
        claims = extract_claims_from_findings(
            findings, "security_agent", claim_index
        )
        all_claims.extend(claims)
        claim_index += len(claims)

        # Areas for verification
        findings = [
            {"statement": area}
            for area in security_result.areas_for_verification
        ]
        claims = extract_claims_from_findings(
            findings, "security_agent", claim_index
        )
        all_claims.extend(claims)
        claim_index += len(claims)

    # Architecture agent findings
    if architecture_result:
        findings = [
            {"statement": issue}
            for issue in architecture_result.potential_issues
        ]
        claims = extract_claims_from_findings(
            findings, "architecture_agent", claim_index
        )
        all_claims.extend(claims)
        claim_index += len(claims)

    # Quality agent findings
    if quality_result:
        findings = [
            {"statement": issue}
            for issue in quality_result.potential_issues
        ]
        claims = extract_claims_from_findings(
            findings, "quality_agent", claim_index
        )
        all_claims.extend(claims)
        claim_index += len(claims)

        findings = [
            {"statement": candidate}
            for candidate in quality_result.refactoring_candidates
        ]
        claims = extract_claims_from_findings(
            findings, "quality_agent", claim_index
        )
        all_claims.extend(claims)
        claim_index += len(claims)

    # Testing agent findings
    if testing_result:
        findings = [
            {"statement": obs}
            for obs in testing_result.observations
        ]
        claims = extract_claims_from_findings(
            findings, "testing_agent", claim_index
        )
        all_claims.extend(claims)
        claim_index += len(claims)

        # Untested components
        findings = [
            {"statement": f"No tests found for {comp}"}
            for comp in testing_result.potentially_untested_components
        ]
        claims = extract_claims_from_findings(
            findings, "testing_agent", claim_index
        )
        all_claims.extend(claims)
        claim_index += len(claims)

    print(f"  [ClaimExtractor] Extracted {len(all_claims)} claims from agent findings.")

    return all_claims
