"""
Developer Action Plan Model.

The main intelligence output: an organized plan telling developers
what to fix NOW, NEXT, and LATER.
"""

from typing import List
from pydantic import BaseModel, Field


class ActionItem(BaseModel):
    """A single item in the developer action plan."""

    finding_id: str = Field(description="Finding ID")
    claim_type: str = Field(description="Type of issue")
    statement: str = Field(description="What the issue is")
    priority: str = Field(description="P0-P4")
    final_score: float = Field(description="Priority score")

    # Action details
    effort: str = Field(default="MEDIUM", description="Fix effort: LOW, MEDIUM, HIGH, VERY_HIGH")
    expected_impact: str = Field(default="MEDIUM", description="Expected impact: LOW, MEDIUM, HIGH, CRITICAL")
    blast_radius: str = Field(default="LOW", description="Blast radius level")
    recommendation_title: str = Field(default="", description="Short fix recommendation")

    # Ordering
    action_order: int = Field(default=0, description="Order within the group")


class ActionPlan(BaseModel):
    """Complete developer action plan for an analysis."""

    analysis_id: int = Field(description="Analysis run ID")

    # Grouped action items
    fix_now: List[ActionItem] = Field(default_factory=list, description="P0+P1: Fix immediately")
    fix_next: List[ActionItem] = Field(default_factory=list, description="P2: Fix this sprint")
    improve_later: List[ActionItem] = Field(default_factory=list, description="P3+P4: Schedule for later")

    # Summary
    total_actions: int = Field(default=0, description="Total actionable items")
    now_count: int = Field(default=0)
    next_count: int = Field(default=0)
    later_count: int = Field(default=0)

    # Overall assessment
    summary: str = Field(default="", description="Summary of the action plan")
