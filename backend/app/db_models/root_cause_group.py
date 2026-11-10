"""SQLAlchemy model for root cause groups. Phase 7."""

from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Text, DateTime
from app.core.database import Base


class RootCauseGroup(Base):
    """Stores grouped root causes from related findings."""

    __tablename__ = "root_cause_groups"

    id = Column(Integer, primary_key=True, autoincrement=True)
    analysis_run_id = Column(Integer, nullable=False)

    group_id = Column(String(100), nullable=False)
    root_cause = Column(String(500), nullable=False)
    category = Column(String(100), nullable=False, default="general")
    finding_count = Column(Integer, nullable=False, default=0)
    severity = Column(String(20), nullable=False, default="MEDIUM")
    priority = Column(String(10), nullable=False, default="P2")
    description = Column(Text, nullable=False, default="")
    fix_suggestion = Column(Text, nullable=False, default="")

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
