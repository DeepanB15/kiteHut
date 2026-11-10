"""SQLAlchemy model for developer action recommendations. Phase 7."""

from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Float, Text, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from app.core.database import Base


class ActionRecommendation(Base):
    """Stores developer action recommendations for each finding."""

    __tablename__ = "action_recommendations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    finding_id = Column(Integer, ForeignKey("findings.id"), nullable=False)

    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=False, default="")
    why = Column(Text, nullable=False, default="")
    best_practice = Column(Text, nullable=False, default="")
    expected_result = Column(Text, nullable=False, default="")
    risk_if_ignored = Column(Text, nullable=False, default="")
    effort = Column(String(20), nullable=False, default="MEDIUM")  # LOW, MEDIUM, HIGH, VERY_HIGH
    confidence = Column(Float, nullable=False, default=0.5)

    # Fix steps stored as JSON text
    fix_steps = Column(Text, nullable=False, default="[]")

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationship
    finding = relationship("Finding", backref="action_recommendations")
