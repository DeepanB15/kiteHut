"""
Evidence Database Model.

Stores evidence items that support or contradict findings.
"""

from datetime import datetime, timezone

from sqlalchemy import String, DateTime, Integer, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Evidence(Base):
    """A piece of evidence linked to a finding."""

    __tablename__ = "evidence"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    finding_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("findings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Evidence details
    evidence_type: Mapped[str] = mapped_column(String(50), nullable=False)
    source: Mapped[str] = mapped_column(String(100), nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), default="")
    line_start: Mapped[int] = mapped_column(Integer, default=0)
    line_end: Mapped[int] = mapped_column(Integer, default=0)
    content: Mapped[str] = mapped_column(Text, default="")
    relation: Mapped[str] = mapped_column(String(20), nullable=False)  # supports, contradicts, neutral
    strength: Mapped[str] = mapped_column(String(20), default="medium")  # strong, medium, weak

    # Metadata
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    finding = relationship("Finding", back_populates="evidence_items")

    def __repr__(self):
        return f"<Evidence [{self.relation}] {self.file_path}>"
