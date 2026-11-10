"""
GitHub Domain Models for RepoLens (Layer 11).
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from app.intelligence.models.findings import Finding


class PRState(str, Enum):
    OPEN = "open"
    CLOSED = "closed"
    MERGED = "merged"


class PullRequestInfo(BaseModel):
    """Structured representation of a GitHub Pull Request."""
    number: int
    title: str
    body: Optional[str] = ""
    head_sha: str
    base_sha: str
    head_branch: str = "feature"
    base_branch: str = "main"
    author: str = "unknown"
    state: PRState = PRState.OPEN
    html_url: str = ""
    diff_url: Optional[str] = None


class PRFileChange(BaseModel):
    """A file changed within a Pull Request."""
    file_path: str
    status: str = "modified"  # added, modified, removed
    additions: int = 0
    deletions: int = 0
    patch: Optional[str] = None


class QualityGateRule(BaseModel):
    """Configurable threshold rules for quality gate evaluation (PRD Section 48)."""
    max_p0: int = 0
    max_p1: int = 0
    max_security_findings: int = 0
    tests_must_pass: bool = True
    confidence_threshold: float = 70.0


class QualityGateCategoryVerdict(BaseModel):
    """Domain category gate verdict."""
    category: str
    passed: bool
    findings_count: int = 0
    message: str = "PASS"


class QualityGateResult(BaseModel):
    """Outcome of Quality Gate evaluation against PR findings and tests."""
    passed: bool
    p0_count: int = 0
    p1_count: int = 0
    security_count: int = 0
    tests_passed: bool = True
    category_verdicts: List[QualityGateCategoryVerdict] = Field(default_factory=list)
    reasons: List[str] = Field(default_factory=list)
    summary: str = "RepoLens Quality Gate: PASS"


class PRReviewReport(BaseModel):
    """Complete PR Review Analysis and Quality Gate Report."""
    pr_number: int
    head_sha: str
    findings: List[Finding] = Field(default_factory=list)
    quality_gate: QualityGateResult
    summary_markdown: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
