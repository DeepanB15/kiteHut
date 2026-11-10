"""
Finding Lifecycle State and Transition Models for RepoLens.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional
import uuid
from pydantic import BaseModel, Field


class LifecycleStatus(str, Enum):
    """Lifecycle state of a verified finding."""
    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    RESOLVED = "RESOLVED"
    IGNORED = "IGNORED"
    FALSE_POSITIVE = "FALSE_POSITIVE"
    ACCEPTED_RISK = "ACCEPTED_RISK"


class LifecycleTransition(BaseModel):
    """Audit log entry for finding status transition."""
    transition_id: str = Field(default_factory=lambda: f"trn_{uuid.uuid4().hex[:8]}")
    from_status: LifecycleStatus
    to_status: LifecycleStatus
    reason: str
    author: str = "agent"
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# Alias for backwards compatibility
LifecycleEvent = LifecycleTransition
