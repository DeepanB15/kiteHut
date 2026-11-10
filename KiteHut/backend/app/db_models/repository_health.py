"""SQLAlchemy model for repository health scores. Phase 7."""

from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Float, Text, DateTime
from app.core.database import Base


class RepositoryHealth(Base):
    """Stores repository health scores per analysis run."""

    __tablename__ = "repository_health"

    id = Column(Integer, primary_key=True, autoincrement=True)
    analysis_run_id = Column(Integer, nullable=False)
    repository_id = Column(Integer, nullable=False)

    overall_score = Column(Float, nullable=False, default=0.0)
    health_level = Column(String(20), nullable=False, default="UNKNOWN")
    total_findings = Column(Integer, nullable=False, default=0)
    critical_findings = Column(Integer, nullable=False, default=0)
    summary = Column(Text, nullable=False, default="")

    security_score = Column(Float, nullable=False, default=100.0)
    architecture_score = Column(Float, nullable=False, default=100.0)
    quality_score = Column(Float, nullable=False, default=100.0)
    testing_score = Column(Float, nullable=False, default=100.0)
    maintainability_score = Column(Float, nullable=False, default=100.0)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
