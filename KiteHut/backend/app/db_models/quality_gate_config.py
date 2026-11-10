"""
Quality Gate Configuration Database Model.

Phase 10: per-repository quality gate rules that override the global
environment defaults (QUALITY_GATE_* settings).
"""

from datetime import datetime, timezone

from sqlalchemy import String, DateTime, Integer, Float, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class QualityGateConfig(Base):
    """Custom quality gate thresholds for one repository."""

    __tablename__ = "quality_gate_configs"

    repository_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("repositories.id", ondelete="CASCADE"),
        primary_key=True,
    )
    critical_limit: Mapped[int] = mapped_column(Integer, default=0)
    security_limit: Mapped[int] = mapped_column(Integer, default=0)
    min_health: Mapped[float] = mapped_column(Float, default=60.0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    def __repr__(self):
        return f"<QualityGateConfig repo={self.repository_id} limits={self.critical_limit}/{self.security_limit}/{self.min_health}>"