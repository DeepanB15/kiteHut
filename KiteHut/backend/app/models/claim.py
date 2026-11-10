"""
Claim Model.

Structured representation of an extracted claim from AI agent findings.
Phase 3, Step 13.
"""

from typing import List, Literal
from pydantic import BaseModel, Field


# Claim categories mapping to specific claim types
CLAIM_CATEGORIES = {
    "security_risk": [
        "hardcoded_secret",
        "missing_authentication",
        "missing_authorization",
        "weak_input_validation",
        "debug_mode_enabled",
        "insecure_configuration",
    ],
    "architecture_issue": [
        "tight_coupling",
        "layer_violation",
        "missing_separation",
        "god_class",
        "circular_dependency",
    ],
    "quality_issue": [
        "code_duplication",
        "large_function",
        "large_class",
        "poor_error_handling",
        "naming_issue",
    ],
    "testing_issue": [
        "missing_tests",
        "low_test_coverage",
        "missing_integration_tests",
        "missing_test_framework",
    ],
}

# Flatten all claim types for validation
ALL_CLAIM_TYPES = [
    ct for types in CLAIM_CATEGORIES.values() for ct in types
]


class Claim(BaseModel):
    """A structured, verifiable claim extracted from an AI agent finding."""

    claim_id: str = Field(
        description="Unique identifier for this claim"
    )
    source_agent: str = Field(
        description="Name of the agent that generated the original finding"
    )
    claim_type: str = Field(
        description="Type of claim (e.g., hardcoded_secret, missing_tests)"
    )
    category: str = Field(
        description="Category: security_risk, architecture_issue, quality_issue, testing_issue"
    )
    statement: str = Field(
        description="The claim statement in natural language"
    )
    target_files: List[str] = Field(
        default_factory=list,
        description="Files referenced in the claim"
    )
    candidate_evidence: List[str] = Field(
        default_factory=list,
        description="Evidence snippets from the original finding"
    )
    verification_required: bool = Field(
        default=True,
        description="Whether this claim requires verification"
    )
