"""
Verified Finding Model.

The final output of Phase 3: a claim with truth classification and confidence.
Phase 3, Step 19.
"""

from typing import List
from pydantic import BaseModel, Field


# Truth classification values
TRUTH_VALUES = [
    "TRUE",
    "LIKELY_TRUE",
    "UNCERTAIN",
    "LIKELY_FALSE",
    "FALSE",
]


class VerifiedFinding(BaseModel):
    """A verified finding with truth classification and confidence score."""

    finding_id: str = Field(
        description="Unique identifier for this verified finding"
    )
    claim_id: str = Field(
        description="The original claim ID"
    )
    original_claim: str = Field(
        description="The original claim statement"
    )
    source_agent: str = Field(
        description="Agent that originally produced the finding"
    )
    claim_type: str = Field(
        description="Type of claim"
    )
    truth_value: str = Field(
        description="Truth classification: TRUE, LIKELY_TRUE, UNCERTAIN, LIKELY_FALSE, FALSE"
    )
    confidence: float = Field(
        ge=0,
        le=100,
        description="Confidence score (0-100)"
    )
    supporting_evidence_count: int = Field(
        default=0,
        description="Number of supporting evidence items"
    )
    contradicting_evidence_count: int = Field(
        default=0,
        description="Number of contradicting evidence items"
    )
    verification_summary: str = Field(
        default="",
        description="Human-readable verification summary"
    )
    verification_methods: List[str] = Field(
        default_factory=list,
        description="Methods used for verification"
    )
    cross_agent_support: bool = Field(
        default=False,
        description="Whether other agents corroborated this finding"
    )
