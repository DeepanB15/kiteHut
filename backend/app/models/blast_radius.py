"""
Blast Radius Model.

Describes what parts of the application could be affected by a finding.
"""

from typing import List
from pydantic import BaseModel, Field


class BlastRadius(BaseModel):
    """Blast radius analysis for a finding."""

    finding_id: str = Field(description="The finding this blast radius relates to")

    # Affected scope
    affected_files: List[str] = Field(default_factory=list, description="Files directly affected")
    affected_modules: List[str] = Field(default_factory=list, description="Modules/packages affected")
    dependent_files: List[str] = Field(default_factory=list, description="Files that import/use the affected code")

    # Classification
    radius_level: str = Field(default="LOW", description="LOW, MEDIUM, HIGH, CRITICAL")
    scope: str = Field(default="local", description="local, module, package, system")

    # Summary
    total_affected: int = Field(default=0, description="Total number of affected files/modules")
    description: str = Field(default="", description="Human-readable blast radius description")
