"""
Root Cause Model.

Groups related findings under a common root cause.
"""

from typing import List
from pydantic import BaseModel, Field


class RootCauseGroup(BaseModel):
    """A group of related findings sharing a common root cause."""

    group_id: str = Field(description="Unique group ID")
    root_cause: str = Field(description="Description of the underlying root cause")
    category: str = Field(description="Category: security, architecture, quality, testing")

    finding_ids: List[str] = Field(default_factory=list, description="Finding IDs in this group")
    finding_count: int = Field(default=0, description="Number of findings in group")

    severity: str = Field(default="MEDIUM", description="Aggregate severity: CRITICAL, HIGH, MEDIUM, LOW")
    priority: str = Field(default="P2", description="Highest priority among grouped findings")

    description: str = Field(default="", description="Detailed explanation of the root cause")
    fix_suggestion: str = Field(default="", description="How to address the root cause")
