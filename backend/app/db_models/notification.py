"""
Notification Database Model.

Phase 10: in-app notifications generated after analyses complete
(e.g. new P0 detected, health dropped, critical issues resolved).
"""

from datetime import datetime, timezone

from sqlalchemy import String, DateTime, Integer, ForeignKey, Text, Boolean
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Notification(Base):
    """A notification about repository health or findings."""

    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    repository_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("repositories.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    # kind: NEW_P0, HEALTH_DROP, CRITICAL_RESOLVED, SECURITY_RISK
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    # severity: info, warning, critical
    severity: Mapped[str] = mapped_column(String(20), default="info")
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    def __repr__(self):
        return f"<Notification #{self.id} [{self.kind}] read={self.read}>"