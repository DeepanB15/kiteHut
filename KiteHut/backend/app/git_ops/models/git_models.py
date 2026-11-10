"""
Git Domain Models for RepoLens (Layer 10).
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class GitFileState(str, Enum):
    MODIFIED = "MODIFIED"
    ADDED = "ADDED"
    DELETED = "DELETED"
    RENAMED = "RENAMED"
    UNTRACKED = "UNTRACKED"
    STAGED = "STAGED"


class GitStatus(BaseModel):
    """Structured representation of repository working tree status."""
    branch: str = "main"
    is_detached: bool = False
    is_dirty: bool = False
    staged_files: List[str] = Field(default_factory=list)
    modified_files: List[str] = Field(default_factory=list)
    untracked_files: List[str] = Field(default_factory=list)
    deleted_files: List[str] = Field(default_factory=list)
    ahead_count: int = 0
    behind_count: int = 0


class GitCommit(BaseModel):
    """Structured representation of a Git commit."""
    commit_hash: str
    short_hash: str
    author_name: str
    author_email: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    message: str
    files_changed: List[str] = Field(default_factory=list)


class BranchInfo(BaseModel):
    """Information regarding a repository branch."""
    name: str
    is_current: bool = False
    commit_hash: Optional[str] = None
    tracking_remote: Optional[str] = None
