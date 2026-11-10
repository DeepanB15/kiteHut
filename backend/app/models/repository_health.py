"""
Repository Health Score Model.

Provides an overall health assessment of the repository.
"""

from pydantic import BaseModel, Field


class CategoryScore(BaseModel):
    """Health score for a specific category."""
    name: str = Field(description="Category name: Security, Architecture, Quality, Testing, Maintainability")
    score: float = Field(ge=0, le=100, description="Score 0-100")
    finding_count: int = Field(default=0, description="Findings in this category")
    top_issue: str = Field(default="", description="Most critical issue in this category")


class RepositoryHealth(BaseModel):
    """Overall repository health assessment."""

    repository_id: int = Field(description="Repository ID")
    analysis_id: int = Field(description="Analysis run ID")

    # Overall score
    overall_score: float = Field(ge=0, le=100, description="Overall health score 0-100")
    health_level: str = Field(description="Excellent, Good, Fair, Poor, Critical")

    # Category breakdown
    security_score: CategoryScore = Field(description="Security health")
    architecture_score: CategoryScore = Field(description="Architecture health")
    quality_score: CategoryScore = Field(description="Code quality health")
    testing_score: CategoryScore = Field(description="Testing health")
    maintainability_score: CategoryScore = Field(description="Maintainability health")

    # Summary
    total_findings: int = Field(default=0, description="Total findings")
    critical_findings: int = Field(default=0, description="P0+P1 findings")
    summary: str = Field(default="", description="Human-readable health summary")
