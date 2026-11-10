"""
Pull Request Finding Database Model.

Phase 9: a single finding detected in a pull request's changed code.
"""

from datetime import datetime, timezone

from sqlalchemy import String, DateTime, Integer, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class PrFinding(Base):
    """A finding detected in a pull request's changed files."""

    __tablename__ = "pr_findings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pr_analysis_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("pr_analyses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)  # CRITICAL/HIGH/MEDIUM/LOW
    priority: Mapped[str] = mapped_column(String(10), nullable=False)  # P0-P4
    file_path: Mapped[str] = mapped_column(String(512), nullable=False)
    line_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    line_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    code_snippet: Mapped[str | None] = mapped_column(Text, nullable=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    recommendation: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(
        String(20), default="rule", nullable=False
    )  # rule, llm
    confidence: Mapped[float] = mapped_column(default=0.0)
    # Phase 10: status lifecycle (OPEN, IN_PROGRESS, RESOLVED, IGNORED,
    # FALSE_POSITIVE, ACCEPTED_RISK)
    status: Mapped[str] = mapped_column(
        String(20), default="OPEN", nullable=False, index=True
    )
    status_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    pr_analysis = relationship("PrAnalysis", back_populates="findings")

    def __repr__(self):
        return f"<PrFinding #{self.id} [{self.severity}] {self.file_path}>"