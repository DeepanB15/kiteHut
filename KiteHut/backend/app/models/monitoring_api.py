"""
Pydantic API models for Continuous Monitoring Guardian Endpoints.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from app.monitoring.models.change_event import ChangeSource, ChangeType


class ChangeEventResponse(BaseModel):
    event_id: str
    source: ChangeSource
    file_path: str
    change_type: ChangeType
    diff_content: Optional[str] = None
    affected_symbols: List[str] = Field(default_factory=list)
    timestamp: datetime
    metadata: Dict[str, Any] = Field(default_factory=dict)


class FindingSummaryResponse(BaseModel):
    finding_id: str
    category: str
    severity: str
    title: str
    description: str
    file_path: Optional[str] = None
    line_number: Optional[int] = None
    priority: Optional[str] = None
    truth_status: Optional[str] = None


class MonitoringReportResponse(BaseModel):
    report_id: str
    timestamp: datetime
    changed_events: List[ChangeEventResponse] = Field(default_factory=list)
    impacted_files: List[str] = Field(default_factory=list)
    triggered_categories: List[str] = Field(default_factory=list)
    new_findings: List[FindingSummaryResponse] = Field(default_factory=list)
    resolved_findings_count: int = 0
    duration_ms: float = 0.0


class MonitoringCheckRequest(BaseModel):
    repository_path: str = Field(default=".", description="Target repository path to check")


class MonitoringStatusResponse(BaseModel):
    repository_path: str
    status: str
    message: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
