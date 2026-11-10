"""
Analysis Job Database Model.

Phase 8: represents an asynchronous analysis job that runs in the
background. Tracks granular pipeline stages so the frontend can poll
and show live progress.

Status flow:
    PENDING -> CLONING -> SCANNING -> ANALYZING -> VERIFYING
    -> SCORING -> SAVING -> COMPLETED
    (any stage -> FAILED on error)
"""

from datetime import datetime, timezone

from sqlalchemy import String, DateTime, Integer, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AnalysisJob(Base):
    """An asynchronous repository analysis job."""

    __tablename__ = "analysis_jobs"

    job_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    repository_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    # REPOSITORY (full repo pipeline) or PR (changed-file analysis)
    job_type: Mapped[str] = mapped_column(
        String(20), default="REPOSITORY", nullable=False
    )
    # Pull request number (only for job_type == "PR")
    pull_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), default="PENDING", nullable=False, index=True
    )  # PENDING, CLONING, SCANNING, ANALYZING, VERIFYING, SCORING, SAVING, COMPLETED, FAILED
    current_stage: Mapped[str | None] = mapped_column(String(30), nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    analysis_run_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("analysis_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Result row id (PrAnalysis.id) for PR jobs
    pr_analysis_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("pr_analyses.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    def __repr__(self):
        return f"<AnalysisJob {self.job_id[:8]} [{self.status}]>"