"""
Evidence Model.

Represents evidence collected from the repository for claim verification.
Phase 3, Step 15/16.
"""

from typing import List, Literal
from pydantic import BaseModel, Field


# Evidence relation types
SUPPORTS = "supports"
CONTRADICTS = "contradicts"
NEUTRAL = "neutral"

# Evidence strength levels
STRONG = "strong"
MEDIUM = "medium"
WEAK = "weak"

# Evidence types
EVIDENCE_TYPES = [
    "source_code",
    "configuration",
    "dependency",
    "structural",
    "test",
    "documentation",
]


class Evidence(BaseModel):
    """A piece of evidence collected from the repository."""

    evidence_id: str = Field(
        description="Unique identifier for this evidence item"
    )
    claim_id: str = Field(
        description="The claim this evidence relates to"
    )
    source: str = Field(
        description="Source of the evidence (scanner, search, file_read, etc.)"
    )
    type: str = Field(
        description="Type of evidence: source_code, configuration, dependency, structural, test, documentation"
    )
    file_path: str = Field(
        description="File path where evidence was found"
    )
    line_start: int = Field(
        default=0,
        description="Starting line number (0 if not applicable)"
    )
    line_end: int = Field(
        default=0,
        description="Ending line number (0 if not applicable)"
    )
    content: str = Field(
        description="Relevant content snippet"
    )
    relation: str = Field(
        description="How this evidence relates to the claim: supports, contradicts, neutral"
    )
    strength: str = Field(
        default=MEDIUM,
        description="Strength of evidence: strong, medium, weak"
    )
