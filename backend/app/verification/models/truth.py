"""
Truth Status and Verification Verdict Models for RepoLens.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


class TruthStatus(str, Enum):
    """Classification of claim veracity based on collected evidence."""
    TRUE = "TRUE"
    PARTIALLY_TRUE = "PARTIALLY_TRUE"
    UNCERTAIN = "UNCERTAIN"
    FALSE = "FALSE"


class VerificationVerdict(BaseModel):
    """Result of verifying a claim or finding against repository evidence."""
    status: TruthStatus
    confidence: float = Field(ge=0.0, le=100.0, description="Verification confidence 0-100")
    explanation: str
    evidence_ids: List[str] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
