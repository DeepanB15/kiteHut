"""
Change Event and Monitoring Report Models for RepoLens (Layer 7).
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid
from pydantic import BaseModel, Field

from app.intelligence.models.findings import Finding, FindingCategory


class ChangeSource(str, Enum):
    """Source that triggered or detected the change event."""
    FILESYSTEM = "FILESYSTEM"
    GIT = "GIT"
    DEPENDENCY = "DEPENDENCY"
    CONFIGURATION = "CONFIGURATION"


class ChangeType(str, Enum):
    """Type of file alteration."""
    MODIFIED = "MODIFIED"
    CREATED = "CREATED"
    DELETED = "DELETED"


class ChangeEvent(BaseModel):
    """Represents a discrete detected change in the workspace."""
    event_id: str = Field(default_factory=lambda: f"ev_{uuid.uuid4().hex[:8]}")
    source: ChangeSource
    file_path: str
    change_type: ChangeType
    diff_content: Optional[str] = None
    affected_symbols: List[str] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Dict[str, Any] = Field(default_factory=dict)


class MonitoringReport(BaseModel):
    """Summary of an incremental monitoring iteration."""
    report_id: str = Field(default_factory=lambda: f"mon_{uuid.uuid4().hex[:8]}")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    changed_events: List[ChangeEvent] = Field(default_factory=list)
    impacted_files: List[str] = Field(default_factory=list)
    triggered_categories: List[FindingCategory] = Field(default_factory=list)
    new_findings: List[Finding] = Field(default_factory=list)
    resolved_findings_count: int = 0
    duration_ms: float = 0.0
