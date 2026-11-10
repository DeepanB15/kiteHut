"""
Evidence Models for RepoLens Trust Engine.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional
import uuid
from pydantic import BaseModel, Field


class EvidenceType(str, Enum):
    """Categorization of collected repository evidence."""
    CODE = "CODE"
    CONFIGURATION = "CONFIGURATION"
    GIT = "GIT"
    TEST = "TEST"
    DEPENDENCY = "DEPENDENCY"
    STRUCTURE = "STRUCTURE"
    RUNTIME = "RUNTIME"


class EvidenceItem(BaseModel):
    """Concrete proof extracted directly from the repository environment."""
    evidence_id: str = Field(default_factory=lambda: f"ev_{uuid.uuid4().hex[:8]}")
    evidence_type: EvidenceType
    source_file: str
    line_number: Optional[int] = None
    snippet: Optional[str] = None
    description: str = ""
    is_corroborating: bool = True
    metadata: Dict[str, Any] = Field(default_factory=dict)
    collected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
