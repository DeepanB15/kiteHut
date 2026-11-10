"""
Patch, Action and Remediation Models for RepoLens (Layer 8).
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid
from pydantic import BaseModel, Field


class FileChangeType(str, Enum):
    MODIFY = "MODIFY"
    CREATE = "CREATE"
    DELETE = "DELETE"


class FilePatch(BaseModel):
    """Represents a patch to an individual file."""
    file_path: str
    change_type: FileChangeType = FileChangeType.MODIFY
    original_content: Optional[str] = None
    new_content: Optional[str] = None
    diff_hunk: Optional[str] = None
    description: str = ""


class ProposedPatch(BaseModel):
    """Multi-file remediation patch proposal for a finding."""
    patch_id: str = Field(default_factory=lambda: f"ptc_{uuid.uuid4().hex[:8]}")
    finding_id: str
    title: str
    description: str
    file_patches: List[FilePatch] = Field(default_factory=list)
    estimated_effort_minutes: int = 15
    risk_level: str = "low"  # low, medium, high
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class TestExecutionResult(BaseModel):
    """Outcome of running test verification."""
    __test__ = False

    passed: bool
    total_tests: int = 0
    passed_tests: int = 0
    failed_tests: int = 0
    output: str = ""
    error_message: Optional[str] = None
    duration_ms: float = 0.0


class ActionResult(BaseModel):
    """Complete outcome of the automated remediation loop."""
    action_id: str = Field(default_factory=lambda: f"act_{uuid.uuid4().hex[:8]}")
    success: bool
    finding_id: str
    applied_patch_id: Optional[str] = None
    modified_files: List[str] = Field(default_factory=list)
    test_results: Optional[TestExecutionResult] = None
    message: str = ""
    error: Optional[str] = None
    rolled_back: bool = False
