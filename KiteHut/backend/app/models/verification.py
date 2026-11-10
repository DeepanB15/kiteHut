"""
Verification Models.

Models for verification plans and verification results.
Phase 3, Step 14/17.
"""

from typing import List
from pydantic import BaseModel, Field


# Verification strategy types
VERIFICATION_STRATEGIES = [
    "secret_scan",
    "pattern_search",
    "dependency_check",
    "structure_check",
    "file_presence_check",
    "test_presence_check",
    "cross_reference_check",
]


class VerificationPlan(BaseModel):
    """A plan for how to verify a specific claim."""

    claim_id: str = Field(
        description="The claim to verify"
    )
    verification_strategy: str = Field(
        description="Strategy type for verification"
    )
    required_evidence: List[str] = Field(
        default_factory=list,
        description="Types of evidence needed"
    )
    search_targets: List[str] = Field(
        default_factory=list,
        description="Specific files or patterns to search for"
    )
    verification_rules: List[str] = Field(
        default_factory=list,
        description="Rules to apply for verification"
    )


class VerificationResult(BaseModel):
    """Result of deterministic verification for a claim."""

    claim_id: str = Field(
        description="The claim that was verified"
    )
    status: str = Field(
        description="Verification status: supported, contradicted, insufficient, uncertain"
    )
    rules_executed: List[str] = Field(
        default_factory=list,
        description="Rules that were executed"
    )
    supporting_evidence: List[str] = Field(
        default_factory=list,
        description="IDs of supporting evidence items"
    )
    contradicting_evidence: List[str] = Field(
        default_factory=list,
        description="IDs of contradicting evidence items"
    )
    neutral_evidence: List[str] = Field(
        default_factory=list,
        description="IDs of neutral evidence items"
    )
