"""
API Response Models.

Pydantic models for the Phase 5 history API responses.
"""

from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field


class RepositoryResponse(BaseModel):
    """Repository list item."""
    id: int
    github_url: str
    owner: str
    name: str
    default_branch: str
    first_analyzed_at: Optional[datetime] = None
    last_analyzed_at: Optional[datetime] = None
    analysis_count: int = 0


class AnalysisRunResponse(BaseModel):
    """Analysis run summary."""
    id: int
    repository_id: int
    status: str
    branch: str
    commit_hash: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    total_findings: int = 0
    error_message: Optional[str] = None
    created_at: Optional[datetime] = None
    # Phase 10: analysis settings
    mode: str = "balanced"
    enabled_agents: Optional[List[str]] = None


class FindingSummary(BaseModel):
    """Finding summary for list views."""
    id: int
    fingerprint: str
    claim_type: str
    category: str
    statement: str
    source_agent: str
    truth_value: str
    confidence: float
    severity: str
    severity_score: float
    final_score: float
    priority: str
    # Phase 10: status lifecycle
    status: str = "OPEN"
    status_note: str | None = None


class EvidenceResponse(BaseModel):
    """Evidence detail."""
    id: int
    evidence_type: str
    source: str
    file_path: str
    line_start: int
    line_end: int
    content: str
    relation: str
    strength: str


class FindingDetail(BaseModel):
    """Full finding detail with evidence."""
    id: int
    fingerprint: str
    claim_type: str
    category: str
    statement: str
    source_agent: str
    truth_value: str
    confidence: float
    severity: str
    severity_score: float
    user_impact: float
    system_impact: float
    business_impact: float
    overall_impact: float
    exploitability: float
    final_score: float
    priority: str
    # Phase 10: status lifecycle
    status: str = "OPEN"
    status_note: str | None = None
    status_updated_at: datetime | None = None
    evidence: List[EvidenceResponse] = []


class AnalysisDetail(BaseModel):
    """Full analysis detail with findings summary."""
    id: int
    repository_id: int
    status: str
    branch: str
    commit_hash: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    total_findings: int = 0
    error_message: Optional[str] = None
    created_at: Optional[datetime] = None
    priority_distribution: dict = {}


class ComparisonSummary(BaseModel):
    """Summary of comparison between two analysis runs."""
    new: int = 0
    resolved: int = 0
    existing: int = 0
    changed: int = 0


class ComparisonResult(BaseModel):
    """Full comparison result between two analysis runs."""
    repository_id: int
    previous_analysis_id: int
    current_analysis_id: int
    summary: ComparisonSummary
    new_findings: List[FindingSummary] = []
    resolved_findings: List[FindingSummary] = []
    existing_findings: List[FindingSummary] = []
    changed_findings: List[dict] = []


class RepositoryListResponse(BaseModel):
    """List of repositories."""
    repositories: List[RepositoryResponse]


class AnalysisListResponse(BaseModel):
    """List of analysis runs."""
    analyses: List[AnalysisRunResponse]


class FindingListResponse(BaseModel):
    """List of findings."""
    findings: List[FindingSummary]
    total: int
