"""
Pull Request Analysis Models (Phase 9).

Request/response models for the GitHub pull request intelligence API.
"""

from datetime import datetime

from pydantic import BaseModel, Field, HttpUrl


class PrAnalysisRequest(BaseModel):
    """Request body for analyzing a pull request."""
    repository_url: HttpUrl = Field(
        ...,
        description="Public GitHub repository URL (https://github.com/owner/repo)",
    )
    pull_number: int = Field(
        ...,
        ge=1,
        le=2_000_000,
        description="Pull request number to analyze",
    )


class PrFindingResponse(BaseModel):
    """A single finding in a pull request analysis."""
    id: int
    category: str
    severity: str
    priority: str
    file_path: str
    line_start: int | None = None
    code_snippet: str | None = None
    message: str
    recommendation: str | None = None
    source: str = "rule"
    confidence: float = 0.0
    status: str = "OPEN"
    status_note: str | None = None


class PrAnalysisSummary(BaseModel):
    """PR analysis list item."""
    id: int
    repository_id: int
    pull_number: int
    pr_title: str | None = None
    pr_url: str | None = None
    status: str
    findings_count: int = 0
    error_message: str | None = None
    comment_posted: bool = False
    # Quality gate verdict (Phase 9): "PASS" / "FAIL" / None
    gate_result: str | None = None
    gate_reasons: list[str] | None = None
    status_check_posted: bool = False
    created_at: datetime
    completed_at: datetime | None = None


class PrAnalysisDetail(PrAnalysisSummary):
    """Full PR analysis detail including findings."""
    base_sha: str | None = None
    head_sha: str | None = None
    findings: list[PrFindingResponse] = []


class PrAnalysisListResponse(BaseModel):
    """List of PR analyses."""
    pr_analyses: list[PrAnalysisSummary]
    total: int


class GithubStatusResponse(BaseModel):
    """GitHub connection status."""
    authenticated: bool
    username: str | None = None
    rate_limit: dict | None = None
    webhook_secret_configured: bool
    pr_comments_enabled: bool
    status_checks_enabled: bool = False
    message: str | None = None


class HealthTrendPoint(BaseModel):
    """One point in a repository's health trend."""
    analysis_run_id: int
    overall_score: float
    health_level: str
    total_findings: int
    critical_findings: int
    created_at: datetime | None = None


class HealthTrendResponse(BaseModel):
    """Health scores across an ordered list of analysis runs."""
    repository_id: int
    trend: list[HealthTrendPoint]