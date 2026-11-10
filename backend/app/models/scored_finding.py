"""
Scored Finding Model.

Phase 4 output: a verified finding enriched with severity, impact,
exploitability analysis, and a final priority score.
"""

from typing import List
from pydantic import BaseModel, Field


# Severity levels
SEVERITY_CRITICAL = "CRITICAL"
SEVERITY_HIGH = "HIGH"
SEVERITY_MEDIUM = "MEDIUM"
SEVERITY_LOW = "LOW"
SEVERITY_INFO = "INFO"

# Priority labels
PRIORITY_P0 = "P0"
PRIORITY_P1 = "P1"
PRIORITY_P2 = "P2"
PRIORITY_P3 = "P3"
PRIORITY_P4 = "P4"


class SeverityResult(BaseModel):
    """Output of severity analysis for a finding."""

    level: str = Field(
        description="Severity level: CRITICAL, HIGH, MEDIUM, LOW, INFO"
    )
    score: float = Field(
        ge=0, le=100,
        description="Numeric severity score (0-100)"
    )
    reasoning: str = Field(
        default="",
        description="Why this severity was assigned"
    )


class ImpactResult(BaseModel):
    """Output of impact analysis for a finding."""

    user_impact: float = Field(
        ge=0, le=100,
        description="Impact on users (0-100)"
    )
    system_impact: float = Field(
        ge=0, le=100,
        description="Impact on system stability/security (0-100)"
    )
    business_impact: float = Field(
        ge=0, le=100,
        description="Impact on business objectives (0-100)"
    )
    overall_impact: float = Field(
        ge=0, le=100,
        description="Weighted overall impact (0-100)"
    )
    reasoning: str = Field(
        default="",
        description="Why these impact scores were assigned"
    )


class ExploitabilityResult(BaseModel):
    """Output of exploitability/risk analysis for a finding."""

    score: float = Field(
        ge=0, le=100,
        description="Exploitability score (0-100, higher = easier to exploit)"
    )
    attack_vector: str = Field(
        default="unknown",
        description="How this could be exploited: network, local, physical, adjacent"
    )
    complexity: str = Field(
        default="unknown",
        description="Attack complexity: low, medium, high"
    )
    reasoning: str = Field(
        default="",
        description="Why this exploitability score was assigned"
    )


class ScoredFinding(BaseModel):
    """A fully scored and prioritized finding."""

    # Identity (links back to verified finding)
    finding_id: str = Field(
        description="Unique identifier"
    )
    claim_id: str = Field(
        description="Original claim ID"
    )
    original_claim: str = Field(
        description="Original claim statement"
    )
    source_agent: str = Field(
        description="Agent that produced the finding"
    )
    claim_type: str = Field(
        description="Type of claim"
    )

    # Phase 3 fields (carried forward)
    truth_value: str = Field(
        description="Truth classification"
    )
    confidence: float = Field(
        ge=0, le=100,
        description="Confidence score (0-100)"
    )

    # Phase 4 scoring
    severity: SeverityResult = Field(
        description="Severity analysis result"
    )
    impact: ImpactResult = Field(
        description="Impact analysis result"
    )
    exploitability: ExploitabilityResult = Field(
        description="Exploitability analysis result"
    )

    # Final scoring
    final_score: float = Field(
        ge=0, le=100,
        description="Final priority score (0-100)"
    )
    priority: str = Field(
        description="Priority level: P0, P1, P2, P3, P4"
    )
    priority_label: str = Field(
        description="Human-readable priority: CRITICAL, HIGH, MEDIUM, LOW, INFO"
    )

    # Summary
    scoring_summary: str = Field(
        default="",
        description="Human-readable scoring breakdown"
    )
