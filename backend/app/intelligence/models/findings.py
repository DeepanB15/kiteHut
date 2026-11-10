"""
Intelligence Finding Models and Schemas for RepoLens.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid
from pydantic import BaseModel, Field


class FindingCategory(str, Enum):
    ARCHITECTURE = "architecture"
    SECURITY = "security"
    CONFIGURATION = "configuration"
    API = "api"
    TESTING = "testing"
    QUALITY = "quality"
    DEPENDENCY = "dependency"
    CODE_REVIEW = "code_review"


class FindingSeverity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class Finding(BaseModel):
    finding_id: str = Field(default_factory=lambda: f"fnd_{uuid.uuid4().hex[:10]}")
    category: FindingCategory
    severity: FindingSeverity
    title: str
    description: str
    file_path: Optional[str] = None
    line_number: Optional[int] = None
    code_snippet: Optional[str] = None
    recommendation: Optional[str] = None
    suggested_fix: Optional[str] = None
    evidence: Optional[str] = None
    agent_name: str = "unknown"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Phase 3 Trust & Scoring Engine fields
    impact: float = 50.0
    exploitability: float = 50.0
    confidence: float = 80.0
    score: float = 0.0
    priority: Optional[str] = "P2"
    truth_status: Optional[str] = "TRUE"
    lifecycle_status: Optional[str] = "OPEN"
    evidence_items: List[Dict[str, Any]] = Field(default_factory=list)
    affected_files: List[str] = Field(default_factory=list)
    affected_components: List[str] = Field(default_factory=list)
    root_cause: Optional[str] = None
    score_breakdown: Optional[Dict[str, Any]] = None


class SpecialistResult(BaseModel):
    agent_name: str
    category: FindingCategory
    findings: List[Finding] = Field(default_factory=list)
    summary: str = ""
    metrics: Dict[str, Any] = Field(default_factory=dict)
    execution_time_ms: float = 0.0


class IntelligenceReport(BaseModel):
    repository_path: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    findings: List[Finding] = Field(default_factory=list)
    summary: str = ""
    category_counts: Dict[str, int] = Field(default_factory=dict)
    severity_counts: Dict[str, int] = Field(default_factory=dict)
    specialist_results: List[SpecialistResult] = Field(default_factory=list)
    health_score: float = 100.0
