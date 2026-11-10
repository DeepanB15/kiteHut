"""
Permission policies and definitions for RepoLens Agent.

Defines permission types, risk levels, decision types, and evaluation rules.
"""

from enum import Enum
from typing import Any, Dict
from pydantic import BaseModel, Field


class PermissionType(str, Enum):
    """Categories of permissions."""
    READ = "READ"
    WRITE = "WRITE"
    EXECUTE = "EXECUTE"
    GIT = "GIT"
    NETWORK = "NETWORK"
    GITHUB = "GITHUB"


class RiskLevel(str, Enum):
    """Risk severity classification."""
    SAFE = "SAFE"                   # Auto-allowed (read-only, inspect)
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"  # Requires explicit approval (modifying files, running commands)
    DANGEROUS = "DANGEROUS"         # Blocked or high-scrutiny (destructive commands, force push)


class DecisionType(str, Enum):
    """User or system decision on a permission request."""
    ALLOW_ONCE = "ALLOW_ONCE"
    ALLOW_FOR_TASK = "ALLOW_FOR_TASK"
    ALLOW_FOR_REPO = "ALLOW_FOR_REPO"
    DENY = "DENY"


class PermissionRequest(BaseModel):
    """A request to authorize an action."""
    request_id: str
    task_id: str
    permission_type: PermissionType
    risk_level: RiskLevel
    tool_name: str
    description: str
    arguments: Dict[str, Any] = Field(default_factory=dict)
    repository_path: str
