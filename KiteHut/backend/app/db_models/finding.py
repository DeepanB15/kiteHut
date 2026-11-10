"""
Finding Database Model.

Stores verified and scored findings for an analysis run.
Includes fingerprinting for cross-run comparison.
"""

from datetime import datetime, timezone

from sqlalchemy import String, DateTime, Integer, Float, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Finding(Base):
    """A verified and scored finding from an analysis run."""

    __tablename__ = "findings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    analysis_run_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("analysis_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Fingerprint for cross-run comparison
    fingerprint: Mapped[str] = mapped_column(String(500), nullable=False, index=True)

    # Claim information
    claim_type: Mapped[str] = mapped_column(String(100), nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    source_agent: Mapped[str] = mapped_column(String(100), nullable=False)

    # Phase 3: Truth & Confidence
    truth_value: Mapped[str] = mapped_column(String(20), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)

    # Phase 4: Scoring
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    severity_score: Mapped[float] = mapped_column(Float, nullable=False)
    user_impact: Mapped[float] = mapped_column(Float, nullable=False)
    system_impact: Mapped[float] = mapped_column(Float, nullable=False)
    business_impact: Mapped[float] = mapped_column(Float, nullable=False)
    overall_impact: Mapped[float] = mapped_column(Float, nullable=False)
    exploitability: Mapped[float] = mapped_column(Float, nullable=False)
    final_score: Mapped[float] = mapped_column(Float, nullable=False)
    priority: Mapped[str] = mapped_column(String(10), nullable=False)

    # Phase 10: status lifecycle (OPEN, IN_PROGRESS, RESOLVED, IGNORED,
    # FALSE_POSITIVE, ACCEPTED_RISK)
    status: Mapped[str] = mapped_column(
        String(20), default="OPEN", nullable=False, index=True
    )
    status_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    status_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Metadata
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    analysis_run = relationship("AnalysisRun", back_populates="findings")
    evidence_items = relationship("Evidence", back_populates="finding", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Finding [{self.priority}] {self.claim_type}>"
