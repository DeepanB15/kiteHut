from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl, field_validator


class RepositoryInfo(BaseModel):
    name: str
    owner: str
    url: str
    local_path: str


# Phase 10: analysis modes (convenience presets for enabled agents)
ANALYSIS_MODES = ("fast", "balanced", "deep")
AGENT_NAMES = ("architecture", "security", "quality", "testing")

# Which agents run by default per mode
MODE_DEFAULT_AGENTS = {
    "fast": ["security"],
    "balanced": ["architecture", "security", "quality", "testing"],
    "deep": ["architecture", "security", "quality", "testing"],
}


class AnalysisRequest(BaseModel):
    repository_url: HttpUrl = Field(
        ...,
        description="Public GitHub repository URL to analyze"
    )
    # Phase 10: analysis settings
    mode: Literal["fast", "balanced", "deep"] = Field(
        "balanced",
        description="Analysis depth preset: fast (security-only scan), "
        "balanced (all agents), deep (all agents + AI recon)",
    )
    enabled_agents: list[str] | None = Field(
        None,
        description="Agents to run: architecture, security, quality, "
        "testing. Defaults to the mode's preset.",
    )

    @field_validator("repository_url")
    @classmethod
    def _validate_url_length(cls, value: HttpUrl) -> HttpUrl:
        if value and len(str(value)) > 2048:
            raise ValueError("Repository URL must be at most 2048 characters")
        return value

    @field_validator("enabled_agents")
    @classmethod
    def _validate_agents(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return value
        normalized = [agent.strip().lower() for agent in value]
        invalid = [a for a in normalized if a not in AGENT_NAMES]
        if invalid:
            raise ValueError(
                f"Unknown agent(s): {', '.join(invalid)}. "
                f"Valid agents: {', '.join(AGENT_NAMES)}"
            )
        return normalized


class AnalysisResponse(BaseModel):
    analysis_id: str
    repository_url: str
    status: Literal["created", "processing", "completed", "failed"]
    created_at: datetime


# ============================================================
# Phase 8 — Async Analysis Jobs
# ============================================================

class AnalysisJobResponse(BaseModel):
    """Response returned when an analysis job is queued (202)."""
    job_id: str
    repository_url: str
    job_type: str = "REPOSITORY"  # REPOSITORY | PR
    pull_number: int | None = None
    status: str  # PENDING, CLONING, SCANNING, ...
    created_at: datetime


class JobStatusResponse(BaseModel):
    """Pollable status of an analysis job."""
    job_id: str
    repository_url: str
    job_type: str = "REPOSITORY"
    pull_number: int | None = None
    status: str
    current_stage: str | None = None
    message: str | None = None
    error_message: str | None = None
    analysis_run_id: int | None = None
    pr_analysis_id: int | None = None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None