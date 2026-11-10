"""
Scoring and Prioritization Models for RepoLens.
"""

from enum import Enum
from typing import Dict, Optional
from pydantic import BaseModel, Field


class Priority(str, Enum):
    """Action priority tier derived from calculated multi-factor score."""
    P0 = "P0"  # 80-100: Critical immediate action required
    P1 = "P1"  # 60-79:  High priority
    P2 = "P2"  # 40-59:  Medium priority
    P3 = "P3"  # 20-39:  Low priority
    P4 = "P4"  # 0-19:   Informational / backlog


class ScoreBreakdown(BaseModel):
    """Explainable components contributing to the final finding score."""
    severity_score: float = Field(ge=0.0, le=100.0, description="Severity weight: 35%")
    impact_score: float = Field(ge=0.0, le=100.0, description="Impact weight: 30%")
    confidence_score: float = Field(ge=0.0, le=100.0, description="Confidence weight: 20%")
    exploitability_score: float = Field(ge=0.0, le=100.0, description="Exploitability weight: 15%")
    final_score: float = Field(ge=0.0, le=100.0, description="Composite score 0-100")
    priority: Priority
    explanation: str = ""
