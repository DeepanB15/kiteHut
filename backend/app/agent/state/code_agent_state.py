"""
Phase 7 — Controlled Code Agent State Model.

Deterministic state machine for a coding task, preserving all required
information through the full workflow: REQUESTED → ... → COMPLETED/FAILED/CANCELLED.

Uses Pydantic BaseModel consistent with existing project patterns
(see agent_state.py for conventions).
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class CodeAgentStatus(str, Enum):
    """Lifecycle status of a code agent task."""
    REQUESTED = "REQUESTED"
    INVESTIGATING = "INVESTIGATING"
    PLANNED = "PLANNED"
    PATCH_PROPOSED = "PATCH_PROPOSED"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    APPROVED = "APPROVED"
    APPLYING = "APPLYING"
    TESTING = "TESTING"
    REVIEWING = "REVIEWING"
    VERIFYING = "VERIFYING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class PatchOperation(str, Enum):
    """Supported patch operations."""
    MODIFY = "MODIFY"
    CREATE = "CREATE"


class ProposedPatch(BaseModel):
    """Structured representation of a proposed change to the repository."""

    file_path: str
    operation: PatchOperation
    old_content: Optional[str] = None
    old_hash: Optional[str] = None
    new_content: str
    reason: str
    snippet: Optional[str] = None  # Small excerpt showing the change

    def is_stale(self, current_content: str) -> bool:
        """
        Return True if the target file changed since the patch was planned.

        Staleness is detected by comparing the current file content against
        the content recorded at planning time:
        - If ``old_hash`` is set, the current content hash must match it.
        - Otherwise, if ``old_content`` is set, it must equal the current content.
        - If neither is recorded, the patch cannot be validated (treated as stale).
        """
        if self.old_hash is not None:
            return self.compute_hash(current_content) != self.old_hash
        if self.old_content is not None:
            return current_content != self.old_content
        # Nothing recorded at planning time → cannot prove the file is unchanged
        return True

    @staticmethod
    def compute_hash(content: str) -> str:
        """SHA-256 content hash used for staleness detection."""
        import hashlib
        return hashlib.sha256(content.encode("utf-8")).hexdigest()


class CodeAgentPlan(BaseModel):
    """Execution plan for a code agent task."""

    task_id: str
    goal: str
    steps: List[Dict[str, Any]] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    status: CodeAgentStatus = CodeAgentStatus.PLANNED


class CodeAgentState(BaseModel):
    """
    Central state tracking a code agent task execution.

    Maintains user intent, repository path, plan, proposed patch,
    approval status, applied changes, test results, and final status.
    """

    task_id: str
    session_id: str
    repository_path: str
    user_goal: str
    status: CodeAgentStatus = CodeAgentStatus.REQUESTED
    plan: Optional[CodeAgentPlan] = None
    proposed_patch: Optional[ProposedPatch] = None
    approval_status: Optional[str] = None  # "approved", "rejected", "cancelled"
    applied_changes: Optional[Dict[str, str]] = Field(default_factory=dict)  # file_path → new_content
    test_result: Optional[Dict[str, Any]] = Field(default_factory=dict)
    review_result: Optional[Dict[str, Any]] = Field(default_factory=dict)
    verification_result: Optional[Dict[str, Any]] = Field(default_factory=dict)
    git_diff: Optional[str] = None
    git_diff_summary: Dict[str, Any] = Field(default_factory=dict)
    retry_count: int = Field(default=0)
    max_retries: int = Field(default=3)
    error_message: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def can_apply_patch(self) -> bool:
        """True only when approval has been explicitly given."""
        return self.approval_status == "approved"

    def can_retry(self) -> bool:
        """True if we haven't exceeded max retries."""
        return self.retry_count < self.max_retries

    def mark_reviewed(self) -> None:
        """Transition from TESTING to REVIEWING."""
        self.status = CodeAgentStatus.REVIEWING
        self.updated_at = datetime.now(timezone.utc)

    def mark_verified(self) -> None:
        """Transition from REVIEWING to VERIFYING."""
        self.status = CodeAgentStatus.VERIFYING
        self.updated_at = datetime.now(timezone.utc)

    def mark_completed(self) -> None:
        """Transition to COMPLETED."""
        self.status = CodeAgentStatus.COMPLETED
        self.updated_at = datetime.now(timezone.utc)

    def mark_failed(self, message: str) -> None:
        """Transition to FAILED."""
        self.status = CodeAgentStatus.FAILED
        self.error_message = message
        self.updated_at = datetime.now(timezone.utc)

    def mark_cancelled(self) -> None:
        """Transition to CANCELLED."""
        self.status = CodeAgentStatus.CANCELLED
        self.updated_at = datetime.now(timezone.utc)