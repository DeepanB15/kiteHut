"""
Repository Database Model.

Represents a GitHub repository that has been analyzed.
"""

from datetime import datetime, timezone

from sqlalchemy import String, DateTime, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Repository(Base):
    """A GitHub repository tracked by RepoLens."""

    __tablename__ = "repositories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    github_url: Mapped[str] = mapped_column(String(500), unique=True, nullable=False, index=True)
    owner: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    default_branch: Mapped[str] = mapped_column(String(255), default="main")
    first_analyzed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    last_analyzed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    analysis_runs = relationship("AnalysisRun", back_populates="repository", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Repository {self.owner}/{self.name}>"
