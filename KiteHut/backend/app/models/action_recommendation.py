"""
Action Recommendation Model.

Represents a recommended fix for a verified finding.
Includes what to change, why, how, and expected result.
"""

from typing import List
from pydantic import BaseModel, Field


class FixStep(BaseModel):
    """A single step in a recommended fix."""
    order: int = Field(description="Step number")
    action: str = Field(description="What to do")
    file_hint: str = Field(default="", description="Suggested file or location")


class ActionRecommendation(BaseModel):
    """A recommended action for a finding."""

    finding_id: str = Field(description="The finding this recommendation addresses")
    claim_type: str = Field(description="Type of claim")

    # What
    title: str = Field(description="Short title of the recommendation")
    description: str = Field(description="Detailed description of what to do")
    why: str = Field(description="Why this fix matters")

    # How
    fix_steps: List[FixStep] = Field(default_factory=list, description="Ordered steps to implement")
    best_practice: str = Field(default="", description="Relevant best practice or reference")

    # Expected
    expected_result: str = Field(default="", description="What the fix achieves")
    risk_if_ignored: str = Field(default="", description="What happens if not fixed")

    # Classification
    effort: str = Field(default="MEDIUM", description="LOW, MEDIUM, HIGH, VERY_HIGH")
    confidence: float = Field(default=80.0, description="How confident we are in this recommendation")
