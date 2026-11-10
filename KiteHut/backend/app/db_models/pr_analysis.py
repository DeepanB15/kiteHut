"""
Pull Request Analysis Database Model.

Phase 9: represents an analysis of a single GitHub pull request.
Findings are scoped to the files changed by the PR.
"""

from datetime import datetime, timezone

from sqlalchemy import String, DateTime, Integer, ForeignKey, Text, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class PrAnalysis(Base):
    """An analysis of a GitHub pull request."""

    __tablename__ = "pr_analyses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    repository_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("repositories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    pull_number: Mapped[int] = mapped_column(Integer, nullable=False)
    pr_title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    pr_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    base_sha: Mapped[str | None] = mapped_column(String(40), nullable=True)
    head_sha: Mapped[str | None] = mapped_column(String(40), nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), default="COMPLETED", nullable=False
    )  # COMPLETED, FAILED
    findings_count: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    comment_posted: Mapped[bool] = mapped_column(default=False)
    # Quality gate verdict (Phase 9): "PASS" / "FAIL" / None (not evaluated)
    gate_result: Mapped[str | None] = mapped_column(String(10), nullable=True)
    # Human-readable reasons when the gate fails (newline-separated)
    gate_reasons: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Whether the commit status check was posted to the PR's head commit
    status_check_posted: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationships
    findings = relationship("PrFinding", back_populates="pr_analysis",
                            cascade="all, delete-orphan")

    def __repr__(self):
        return f"<PrAnalysis #{self.id} PR #{self.pull_number} [{self.status}]>"