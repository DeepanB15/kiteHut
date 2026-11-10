"""
Agent State and Execution Models for RepoLens.

Defines schemas for task status, steps, tool invocations, results, and overall agent state.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, ClassVar, Dict, List, Optional
from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    """Lifecycle status of an agent task."""
    PENDING = "PENDING"
    PLANNING = "PLANNING"
    RUNNING = "RUNNING"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class StepStatus(str, Enum):
    """Lifecycle status of an individual plan step."""
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class ToolCall(BaseModel):
    """A tool call requested or executed by the agent."""
    call_id: str = Field(description="Unique identifier for this tool call")
    tool_name: str = Field(description="Name of the target tool")
    arguments: Dict[str, Any] = Field(default_factory=dict, description="Arguments passed to the tool")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ToolResult(BaseModel):
    """Result of a tool execution."""
    call_id: str
    tool_name: str
    success: bool
    output: Optional[str] = None
    error: Optional[str] = None
    duration_ms: float = 0.0
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PlanStep(BaseModel):
    """A discrete step in an execution plan."""
    step_id: int
    description: str
    tool_name: Optional[str] = None
    arguments: Dict[str, Any] = Field(default_factory=dict)
    expected_output: Optional[str] = None
    status: StepStatus = StepStatus.PENDING
    result: Optional[ToolResult] = None
    error: Optional[str] = None


class Plan(BaseModel):
    """A structured plan containing an ordered sequence of steps."""
    task_id: str
    goal: str
    steps: List[PlanStep] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    status: TaskStatus = TaskStatus.PENDING

    # Reference to the AgentTask this plan belongs to
    agent_task: Optional["AgentTask"] = Field(
        default=None,
        description="The AgentTask this plan belongs to",
    )

    model_config = {"validate_by_name": True}


class AgentObservation(BaseModel):
    """Observation recorded during agent execution."""
    step_id: int
    observation: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ============================================================
# Step 2: Agent Task Model
# ============================================================

class AgentTask(BaseModel):
    """Model representing what the user wants the agent to accomplish."""

    task_id: str = Field(
        description="Unique identifier for this task. Deterministic or explicitly supplied during testing."
    )
    query: str = Field(
        description="The user's original query or question"
    )
    task_type: str = Field(
        description="Type of task: QUESTION, REVIEW, INVESTIGATE, EXPLAIN, TEST, FIX"
    )
    repository_path: str = Field(
        description="Path to the repository being examined"
    )
    constraints: Dict[str, str] = Field(
        default_factory=dict,
        description="Constraints on the agent's work"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata"
    )

    model_config = {"validate_by_name": True}


# ============================================================
# Step 3: Task Types Taxonomy
# ============================================================

# Explicit task type constants for the Phase 9.1 taxonomy
TASK_TYPE_QUESTION = "QUESTION"
TASK_TYPE_REVIEW = "REVIEW"
TASK_TYPE_INVESTIGATE = "INVESTIGATE"
TASK_TYPE_EXPLAIN = "EXPLAIN"
TASK_TYPE_TEST = "TEST"
TASK_TYPE_FIX = "FIX"

_VALID_TASK_TYPES = {
    TASK_TYPE_QUESTION,
    TASK_TYPE_REVIEW,
    TASK_TYPE_INVESTIGATE,
    TASK_TYPE_EXPLAIN,
    TASK_TYPE_TEST,
    TASK_TYPE_FIX,
}


def is_valid_task_type(task_type: str) -> bool:
    """Check if a task type is valid per the Phase 9.1 taxonomy."""
    return task_type in _VALID_TASK_TYPES


# Default task type if none supplied
DEFAULT_TASK_TYPE = TASK_TYPE_QUESTION


# ============================================================
# Step 4: Agent Lifecycle / Status Model
# ============================================================

class AgentStatus(str, Enum):
    """Explicit agent lifecycle status model."""

    IDLE = "IDLE"
    INITIALIZING = "INITIALIZING"
    PLANNING = "PLANNING"
    EXECUTING = "EXECUTING"
    VERIFYING = "VERIFYING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"

    # Valid transitions documentation
    """
    Valid transitions:

    IDLE
     ↓
    INITIALIZING
     ↓
    PLANNING
     ↓
    EXECUTING
     ↓
    VERIFYING
     ↓
    COMPLETED

    Failure/cancellation paths:

    EXECUTING -> FAILED (with error)
    EXECUTING -> CANCELLED (requested cancellation)
    VERIFYING -> FAILED (verification failure)
    VERIFYING -> COMPLETED (verification passed)

    Any status -> CANCELLED (forced cancellation)
    FAILED and CANCELLED are terminal states
    COMPLETED is a terminal state
    """

    model_config = {"validate_by_name": True}


# ============================================================
# Step 5: Agent Step / Observation Model
# ============================================================

class AgentStep(BaseModel):
    """Model representing an individual agent step."""

    step_id: int = Field(
        description="Unique identifier for this step within an iteration"
    )
    iteration: int = Field(
        description="Iteration number this step belongs to"
    )
    action_type: str = Field(
        description="Type of action: REASON, RETRIEVE, TOOL_CALL, OBSERVE, VERIFY, RESPOND"
    )
    description: str = Field(
        description="Human-readable description of the step"
    )
    input: Dict[str, Any] = Field(
        default_factory=dict,
        description="Input data for this step"
    )
    output: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Output data from this step (if completed)"
    )
    status: StepStatus = Field(
        default=StepStatus.PENDING,
        description="Status of this step"
    )
    error: Optional[str] = Field(
        default=None,
        description="Error message if step failed"
    )

    model_config = {"validate_by_name": True}

    # Valid action type constants (ClassVar so Pydantic does not treat them as fields)
    ACTION_REASON: ClassVar[str] = "REASON"
    ACTION_RETRIEVE: ClassVar[str] = "RETRIEVE"
    ACTION_TOOL_CALL: ClassVar[str] = "TOOL_CALL"
    ACTION_OBSERVE: ClassVar[str] = "OBSERVE"
    ACTION_VERIFY: ClassVar[str] = "VERIFY"
    ACTION_RESPOND: ClassVar[str] = "RESPOND"

    _VALID_ACTION_TYPES: ClassVar[set] = {
        "REASON",
        "RETRIEVE",
        "TOOL_CALL",
        "OBSERVE",
        "VERIFY",
        "RESPOND",
    }

    @classmethod
    def is_valid_action_type(cls, action_type: str) -> bool:
        """Check if an action type is valid."""
        return action_type in cls._VALID_ACTION_TYPES


# ============================================================
# Step 7: Evidence Reference Model
# ============================================================

class EvidenceReference(BaseModel):
    """Lightweight reference tracking evidence for claim verification."""

    evidence_id: str = Field(
        description="Unique identifier for this evidence reference"
    )
    source_type: str = Field(
        description="Type of source (e.g., source_code, configuration, dependency, structural, test, documentation)"
    )
    source: str = Field(
        description="Source identifier or path"
    )
    location: str = Field(
        description="Location within the source (e.g., file_path:line_range)"
    )
    description: str = Field(
        description="Description of what this evidence represents"
    )

    model_config = {"validate_by_name": True}


# ============================================================
# Step 8: Claim Reference Model
# ============================================================

class AgentClaim(BaseModel):
    """Lightweight claim representation linking claims to evidence and verification."""

    claim_id: str = Field(
        description="Unique identifier for this claim"
    )
    text: str = Field(
        description="The claim statement in natural language"
    )
    status: str = Field(
        description="Claim status: UNVERIFIED, VERIFIED, UNSUPPORTED, INCONCLUSIVE"
    )
    evidence_ids: List[str] = Field(
        default_factory=list,
        description="IDs of evidence items supporting this claim"
    )
    confidence: float = Field(
        default=0.5,
        description="Confidence score 0.0 to 1.0"
    )

    model_config = {"validate_by_name": True}

    # Claim status constants (ClassVar so Pydantic does not treat them as fields)
    STATUS_UNVERIFIED: ClassVar[str] = "UNVERIFIED"
    STATUS_VERIFIED: ClassVar[str] = "VERIFIED"
    STATUS_UNSUPPORTED: ClassVar[str] = "UNSUPPORTED"
    STATUS_INCONCLUSIVE: ClassVar[str] = "INCONCLUSIVE"

    _VALID_CLAIM_STATUSES: ClassVar[set] = {
        "UNVERIFIED",
        "VERIFIED",
        "UNSUPPORTED",
        "INCONCLUSIVE",
    }

    model_config = {"validate_by_name": True}




def is_valid_claim_status(status: str) -> bool:
    """Check if a claim status is valid."""
    return status in AgentClaim._VALID_CLAIM_STATUSES

# ============================================================
# Central AgentState (existing + Phase 9.1 extension)
# ============================================================

class AgentState(BaseModel):
    """
    Central state tracking an agent task execution.
    Maintains user intent, repository path, plan, tool history, status,
    and Phase 9.1 task/observation/claim/evidence contracts.
    """
    task_id: str
    session_id: str
    repository_path: str
    user_goal: str
    status: TaskStatus = TaskStatus.PENDING
    plan: Optional[Plan] = None
    current_step_index: int = 0
    tool_history: List[ToolResult] = Field(default_factory=list)
    observations: List[AgentObservation] = Field(default_factory=list)
    context_files: List[str] = Field(default_factory=list)
    error_message: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Phase 9.1 extension: reference to AgentTask (optional but expected)
    task: Optional[AgentTask] = Field(
        default=None,
        description="The AgentTask this state belongs to",
    )

    # Phase 9.1 extension: agent steps (individual step records)
    steps: List[AgentStep] = Field(
        default_factory=list,
        description="Individual agent steps executed",
    )

    # Phase 9.1 extension: claims with evidence references
    claims: List[AgentClaim] = Field(
        default_factory=list,
        description="Claims made during execution with evidence tracking",
    )

    # Phase 9.1 extension: evidence references
    evidence_refs: List[EvidenceReference] = Field(
        default_factory=list,
        description="Evidence references for verification",
    )

    # Phase 9.1 extension: retrieved context (lightweight, not duplicating full RAG objects)
    retrieved_context: List[str] = Field(
        default_factory=list,
        description="References to retrieved context items",
    )

    # Phase 9.1 extension: final answer
    final_answer: Optional[str] = Field(
        default=None,
        description="Final answer when status is COMPLETED",
    )

    model_config = {"validate_by_name": True}


# ============================================================
# Step 9: State Invariants
# ============================================================

def validate_agent_state_invariants(state: AgentState) -> List[str]:
    """Validate basic invariants for AgentState."""
    errors: List[str] = []

    # Iteration must never be negative
    if state.current_step_index < 0:
        errors.append("current_step_index must not be negative")

    # Every AgentState must reference exactly one AgentTask
    # (task_id is required field, enforced by Pydantic)

    # If state is COMPLETED, it should have a final answer or error
    if state.status == AgentStatus.COMPLETED:
        if not state.error_message and not state.observations:
            errors.append("COMPLETED state should have a final outcome")

    # If state is FAILED, it should contain an error/reason
    if state.status == AgentStatus.FAILED:
        if not state.error_message:
            errors.append("FAILED state should contain an error_message")

    # CANCELLED state should be distinguishable from FAILED
    # (Already enforced by different enum values)

    # Evidence references must be structurally valid if present
    # (Handled by Pydantic validation of EvidenceReference objects)

    # Claims should be structurally valid even if currently unverified
    # (Already enforced by Pydantic validation of AgentClaim objects)

    return errors


# ============================================================
# Step 10: Serialization Support
# ============================================================

def serialize_agent_state(state: AgentState) -> Dict[str, Any]:
    """Serialize AgentState to a dict suitable for JSON round-trip."""
    data = {
        "task_id": state.task_id,
        "session_id": state.session_id,
        "repository_path": state.repository_path,
        "user_goal": state.user_goal,
        "status": state.status.value if isinstance(state.status, AgentStatus) else state.status,
        "plan": state.plan.model_dump() if state.plan else None,
        "current_step_index": state.current_step_index,
        "tool_history": [t.model_dump() for t in state.tool_history],
        "observations": [
            {
                "step_id": o.step_id,
                "observation": o.observation,
                "timestamp": o.timestamp.isoformat() if o.timestamp else None,
            }
            for o in state.observations
        ],
        "context_files": state.context_files,
        "error_message": state.error_message,
        "created_at": state.created_at.isoformat() if state.created_at else None,
        "updated_at": state.updated_at.isoformat() if state.updated_at else None,
        # Phase 9.1 new fields
        "task": state.task.model_dump() if hasattr(state, 'task') and state.task else None,
        "steps": [s.model_dump() for s in state.steps],
        "claims": [c.model_dump() for c in state.claims],
        "evidence_refs": [e.model_dump() for e in state.evidence_refs],
        "retrieved_context": state.retrieved_context,
        "final_answer": state.final_answer,
    }
    return data


def deserialize_agent_state(data: Dict[str, Any]) -> AgentState:
    """Deserialize AgentState from dict, preserving important fields."""
    # Parse status
    status_val = data.get("status", "PENDING")
    # Support both AgentStatus and TaskStatus values for backward compatibility
    valid_statuses = {
        AgentStatus.IDLE.value,
        AgentStatus.INITIALIZING.value,
        AgentStatus.PLANNING.value,
        AgentStatus.EXECUTING.value,
        AgentStatus.VERIFYING.value,
        AgentStatus.COMPLETED.value,
        AgentStatus.FAILED.value,
        AgentStatus.CANCELLED.value,
        TaskStatus.PENDING.value,
        TaskStatus.RUNNING.value,
        TaskStatus.WAITING_APPROVAL.value,
        TaskStatus.COMPLETED.value,
        TaskStatus.FAILED.value,
        TaskStatus.CANCELLED.value,
    }
    status_str = status_val if isinstance(status_val, str) else str(status_val)
    if status_str in valid_statuses:
        status = AgentStatus(status_str) if status_str in {
            a.value for a in AgentStatus
        } else TaskStatus(status_str)
    else:
        # Default to the existing TaskStatus PENDING for backward compatibility
        status = TaskStatus.PENDING

    # Parse plan
    plan_data = data.get("plan")
    plan = Plan.model_validate(plan_data) if plan_data else None

    # Parse observations
    observations_data = data.get("observations", [])
    observations = []
    for o in observations_data:
        observations.append(AgentObservation(
            step_id=o.get("step_id", 0),
            observation=o.get("observation", ""),
            timestamp=(
                datetime.fromisoformat(o["timestamp"])
                if o.get("timestamp")
                else datetime.now(timezone.utc)
            ),
        ))

    # Parse tool history
    tool_history_data = data.get("tool_history", [])
    tool_history = []
    for t in tool_history_data:
        tool_history.append(ToolResult(
            call_id=t.get("call_id", ""),
            tool_name=t.get("tool_name", ""),
            success=t.get("success", False),
            output=t.get("output"),
            error=t.get("error"),
            duration_ms=t.get("duration_ms", 0.0),
            created_at=(
                datetime.fromisoformat(t["created_at"]) if t.get("created_at") else datetime.now(timezone.utc)
            ),
        ))

    # Parse new Phase 9.1 fields
    task_data = data.get("task")
    task = None
    if task_data:
        task = AgentTask(**task_data)

    # Parse steps
    steps_data = data.get("steps", [])
    steps = [AgentStep(**s) for s in steps_data if s]

    # Parse claims
    claims_data = data.get("claims", [])
    claims = [AgentClaim(**c) for c in claims_data if c]

    # Parse evidence_refs
    evidence_refs_data = data.get("evidence_refs", [])
    evidence_refs = [EvidenceReference(**e) for e in evidence_refs_data if e]

    # Build AgentState
    state = AgentState(
        task_id=data.get("task_id", ""),
        session_id=data.get("session_id", ""),
        repository_path=data.get("repository_path", ""),
        user_goal=data.get("user_goal", ""),
        status=status,
        plan=plan,
        current_step_index=data.get("current_step_index", 0),
        tool_history=tool_history,
        observations=observations,
        context_files=data.get("context_files", []),
        error_message=data.get("error_message"),
        created_at=(
            datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.now(timezone.utc)
        ),
        updated_at=(
            datetime.fromisoformat(data["updated_at"]) if data.get("updated_at") else datetime.now(timezone.utc)
        ),
        task=task,
        steps=steps,
        claims=claims,
        evidence_refs=evidence_refs,
        retrieved_context=data.get("retrieved_context", []),
        final_answer=data.get("final_answer"),
    )

    # Assign task if present
    if task:
        state.task = task  # type: ignore[attr-defined]

    return state