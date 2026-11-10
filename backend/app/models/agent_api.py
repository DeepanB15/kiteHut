"""
Pydantic API models for Agent Core and Guardian Endpoints.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from app.agent.state.agent_state import StepStatus, TaskStatus


class CreateAgentTaskRequest(BaseModel):
    repository_path: str = Field(..., description="Path to target repository on disk")
    user_goal: str = Field(..., description="Intent / user goal for the agent task")
    session_id: Optional[str] = Field(None, description="Optional grouping session ID")
    auto_allow_safe: bool = Field(True, description="Automatically allow safe read-only operations")
    auto_allow_all: bool = Field(False, description="Bypass all approval prompts (autonomous mode)")


class ToolResultResponse(BaseModel):
    call_id: str
    tool_name: str
    success: bool
    output: Optional[str] = None
    error: Optional[str] = None
    duration_ms: float = 0.0
    created_at: datetime


class PlanStepResponse(BaseModel):
    step_id: int
    description: str
    tool_name: Optional[str] = None
    arguments: Dict[str, Any] = Field(default_factory=dict)
    expected_output: Optional[str] = None
    status: StepStatus = StepStatus.PENDING
    result: Optional[ToolResultResponse] = None
    error: Optional[str] = None


class PlanResponse(BaseModel):
    task_id: str
    goal: str
    steps: List[PlanStepResponse] = Field(default_factory=list)
    created_at: datetime
    status: TaskStatus = TaskStatus.PENDING


class AgentObservationResponse(BaseModel):
    step_id: int
    observation: str
    timestamp: datetime


class AgentTaskResponse(BaseModel):
    task_id: str
    session_id: str
    repository_path: str
    user_goal: str
    status: TaskStatus
    plan: Optional[PlanResponse] = None
    current_step_index: int = 0
    tool_history: List[ToolResultResponse] = Field(default_factory=list)
    observations: List[AgentObservationResponse] = Field(default_factory=list)
    context_files: List[str] = Field(default_factory=list)
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class AgentTaskListResponse(BaseModel):
    tasks: List[AgentTaskResponse] = Field(default_factory=list)
    total: int = 0


class TaskApprovalRequest(BaseModel):
    decision: str = Field(..., description="Decision: ALLOW_ONCE, ALLOW_FOR_TASK, ALLOW_FOR_REPO, DENY")
    tool_name: Optional[str] = Field(None, description="Optional tool name if granting scoped permission")


class TaskRollbackResponse(BaseModel):
    task_id: str
    restored_files: List[str] = Field(default_factory=list)
    success: bool
    message: str


class RemediationRequest(BaseModel):
    repository_path: str = Field(..., description="Repository directory path")
    finding_id: Optional[str] = Field(None, description="Finding ID to remediate")
    finding_data: Optional[Dict[str, Any]] = Field(None, description="Direct finding payload to remediate")
    auto_approve: bool = Field(True, description="Auto-approve permission requests")
    run_tests: bool = Field(True, description="Run test suite to verify fix and auto-rollback on failure")
    test_paths: Optional[List[str]] = Field(None, description="Specific test file paths to run")


class RemediationResponse(BaseModel):
    action_id: str
    finding_id: str
    success: bool
    applied_patch_id: Optional[str] = None
    modified_files: List[str] = Field(default_factory=list)
    test_results: Optional[Dict[str, Any]] = None
    message: str
    error: Optional[str] = None
    rolled_back: bool = False
