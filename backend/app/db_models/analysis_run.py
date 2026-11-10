"""
Analysis Run Database Model.

Represents a single analysis execution against a repository.
Each analysis creates a new immutable run.
"""

from datetime import datetime, timezone

from sqlalchemy import String, DateTime, Integer, Float, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class AnalysisRun(Base):
    """An analysis run against a repository."""

    __tablename__ = "analysis_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    repository_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("repositories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        default="PENDING",
        nullable=False,
    )  # PENDING, RUNNING, COMPLETED, FAILED
    branch: Mapped[str] = mapped_column(String(255), default="main")
    commit_hash: Mapped[str | None] = mapped_column(String(40), nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_findings: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Phase 10: analysis settings
    mode: Mapped[str] = mapped_column(String(20), default="balanced")
    # JSON-encoded list of enabled agents
    enabled_agents: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    repository = relationship("Repository", back_populates="analysis_runs")
    findings = relationship("Finding", back_populates="analysis_run", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<AnalysisRun #{self.id} [{self.status}]>"
