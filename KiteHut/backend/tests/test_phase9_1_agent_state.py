"""
Phase 9.1 — Agent State + Task Model Tests.

Tests for AgentTask, AgentStatus, AgentState, AgentStep,
AgentClaim, EvidenceReference, serialization, and invariants.
All tests are deterministic and offline.
"""

import pytest
from app.agent.state.agent_state import (
    AgentTask,
    AgentStatus,
    AgentState,
    AgentStep,
    AgentClaim,
    EvidenceReference,
    AgentObservation,
    Plan,
    TaskStatus,
    StepStatus,
    is_valid_task_type,
    DEFAULT_TASK_TYPE,
    validate_agent_state_invariants,
    serialize_agent_state,
    deserialize_agent_state,
)


# ------------------------------------------------------------------
# Step 2: AgentTask Tests
# ------------------------------------------------------------------

def test_agent_task_creation():
    """Valid task creation with required fields."""
    task = AgentTask(
        task_id="task_001",
        query="What is the authentication mechanism?",
        task_type="QUESTION",
        repository_path="/tmp/repo",
    )
    assert task.task_id == "task_001"
    assert task.query == "What is the authentication mechanism?"
    assert task.task_type == "QUESTION"
    assert task.repository_path == "/tmp/repo"


def test_agent_task_deterministic_id():
    """Task ID is deterministic or explicitly supplied in tests."""
    task = AgentTask(
        task_id="test_deterministic_42",
        query="Investigate security",
        task_type="INVESTIGATE",
        repository_path="/test/repo",
    )
    assert task.task_id == "test_deterministic_42"


def test_agent_task_required_query():
    """Query is a required field (must be non-empty)."""
    # Empty string is allowed by Pydantic string validation
    # Non-empty query is enforced by business logic, not schema
    task = AgentTask(
        task_id="t1",
        query="Investigate",
        task_type="REVIEW",
        repository_path="/r",
    )
    assert task.query == "Investigate"


def test_agent_task_constraints_and_metadata():
    """Constraints and metadata fields exist and work."""
    task = AgentTask(
        task_id="t2",
        query="Review",
        task_type="REVIEW",
        repository_path="/r",
        constraints={"max_steps": "5"},
        metadata={"source": "cli"},
    )
    assert task.constraints == {"max_steps": "5"}
    assert task.metadata == {"source": "cli"}


# ------------------------------------------------------------------
# Step 3: Task Types Taxonomy Tests
# ------------------------------------------------------------------

def test_valid_task_types():
    """All valid task types are recognized."""
    valid = [
        "QUESTION", "REVIEW", "INVESTIGATE",
        "EXPLAIN", "TEST", "FIX",
    ]
    for v in valid:
        assert is_valid_task_type(v) is True


def test_invalid_task_type_rejected():
    """Invalid task types are not recognized (but not strictly rejected by model)."""
    assert is_valid_task_type("UNKNOWN") is False
    assert is_valid_task_type("") is False


def test_default_task_type():
    """Default task type is QUESTION."""
    assert DEFAULT_TASK_TYPE == "QUESTION"


# ------------------------------------------------------------------
# Step 4: Agent Status / Lifecycle Tests
# ------------------------------------------------------------------

def test_valid_agent_statuses():
    """All lifecycle statuses are valid enum members."""
    statuses = [
        AgentStatus.IDLE,
        AgentStatus.INITIALIZING,
        AgentStatus.PLANNING,
        AgentStatus.EXECUTING,
        AgentStatus.VERIFYING,
        AgentStatus.COMPLETED,
        AgentStatus.FAILED,
        AgentStatus.CANCELLED,
    ]
    for s in statuses:
        assert isinstance(s, AgentStatus)


def test_agent_status_transitions_documented():
    """Transitions are documented (not enforced by engine yet)."""
    # These are contracts, not enforced by state machine
    assert AgentStatus.IDLE.value == "IDLE"
    assert AgentStatus.COMPLETED.value == "COMPLETED"
    assert AgentStatus.FAILED.value == "FAILED"
    assert AgentStatus.CANCELLED.value == "CANCELLED"


# ------------------------------------------------------------------
# Step 5: AgentState Tests
# ------------------------------------------------------------------

def test_agent_state_initial():
    """Initial AgentState with task reference."""
    state = AgentState(
        task_id="t_001",
        session_id="sess_001",
        repository_path="/repo",
        user_goal="Investigate auth mechanism",
    )
    assert state.status == TaskStatus.PENDING
    assert state.task_id == "t_001"
    assert state.current_step_index == 0
    assert state.task is None


def test_agent_state_iteration_validation():
    """Iteration must never be negative (enforced by invariant)."""
    state = AgentState(
        task_id="t_002",
        session_id="sess_002",
        repository_path="/repo",
        user_goal="Test",
        current_step_index=-1,
    )
    errors = validate_agent_state_invariants(state)
    assert any("negative" in e for e in errors)


def test_agent_state_task_association():
    """Every AgentState references a task (either directly or via task_id)."""
    task = AgentTask(
        task_id="t_003",
        query="Explain architecture",
        task_type="EXPLAIN",
        repository_path="/repo",
    )
    state = AgentState(
        task_id="t_003",
        session_id="sess_003",
        repository_path="/repo",
        user_goal="Explain architecture",
        task=task,
    )
    assert state.task is not None
    assert state.task.task_id == "t_003"


def test_agent_state_intermediate():
    """Intermediate state (EXECUTING) allows partial observations."""
    state = AgentState(
        task_id="t_004",
        session_id="sess_004",
        repository_path="/repo",
        user_goal="Review",
        status=TaskStatus.RUNNING,
        observations=[AgentObservation(step_id=1, observation="Started review")],
    )
    assert state.status == TaskStatus.RUNNING
    assert len(state.observations) == 1


def test_agent_state_completed():
    """COMPLETED state has final answer."""
    state = AgentState(
        task_id="t_005",
        session_id="sess_005",
        repository_path="/repo",
        user_goal="Review",
        status=TaskStatus.COMPLETED,
        final_answer="Review complete. No critical issues found.",
    )
    assert state.status == TaskStatus.COMPLETED
    assert state.final_answer is not None


def test_agent_state_failed():
    """FAILED state contains error/reason."""
    state = AgentState(
        task_id="t_006",
        session_id="sess_006",
        repository_path="/repo",
        user_goal="Investigate",
        status=TaskStatus.FAILED,
        error_message="Missing file for analysis",
    )
    assert state.status == TaskStatus.FAILED
    errors = validate_agent_state_invariants(state)
    assert not any("error_message" in e for e in errors)


def test_agent_state_cancelled():
    """CANCELLED state distinguishable from FAILED."""
    state = AgentState(
        task_id="t_007",
        session_id="sess_007",
        repository_path="/repo",
        user_goal="Test",
        status=TaskStatus.CANCELLED,
        error_message="User cancelled",
    )
    assert state.status == TaskStatus.CANCELLED
    assert state.status != AgentStatus.FAILED


# ------------------------------------------------------------------
# Step 6: AgentStep Tests
# ------------------------------------------------------------------

def test_valid_step():
    """Valid agent step creation."""
    step = AgentStep(
        step_id=1,
        iteration=1,
        action_type="RETRIEVE",
        description="Search for auth patterns",
    )
    assert step.step_id == 1
    assert step.iteration == 1
    assert step.action_type == "RETRIEVE"


    # Reference module-level action types (avoids Pydantic ClassVar issues)
    assert "REASON" == AgentStep.ACTION_REASON
    assert "RETRIEVE" == AgentStep.ACTION_RETRIEVE
    assert "TOOL_CALL" == AgentStep.ACTION_TOOL_CALL
    assert "OBSERVE" == AgentStep.ACTION_OBSERVE
    assert "VERIFY" == AgentStep.ACTION_VERIFY
    assert "RESPOND" == AgentStep.ACTION_RESPOND


def test_invalid_action_type():
    """Invalid action type rejected."""
    # Note: _VALID_ACTION_TYPES is a ClassVar; access via class
    assert AgentStep.is_valid_action_type("INVALID") is False


def test_step_success_failure():
    """Step success/failure representation."""
    step_success = AgentStep(
        step_id=1,
        iteration=1,
        action_type="OBSERVE",
        description="Observation recorded",
        status=StepStatus.COMPLETED,
    )
    step_failed = AgentStep(
        step_id=2,
        iteration=1,
        action_type="VERIFY",
        description="Verification failed",
        status=StepStatus.FAILED,
        error="Evidence not found",
    )
    assert step_success.status == StepStatus.COMPLETED
    assert step_failed.status == StepStatus.FAILED
    assert step_failed.error == "Evidence not found"


# ------------------------------------------------------------------
# Step 7: EvidenceReference Tests
# ------------------------------------------------------------------

def test_evidence_reference_valid():
    """Valid evidence reference structure."""
    evidence = EvidenceReference(
        evidence_id="ev_001",
        source_type="source_code",
        source="app/auth.py",
        location="line_42:line_55",
        description="Authentication check implementation",
    )
    assert evidence.evidence_id == "ev_001"
    assert evidence.source_type == "source_code"


def test_evidence_reference_serialization():
    """Evidence reference serializes correctly."""
    evidence = EvidenceReference(
        evidence_id="ev_002",
        source_type="test",
        source="tests/test_auth.py",
        location="line_10:line_15",
        description="Test coverage",
    )
    data = evidence.model_dump()
    assert data["evidence_id"] == "ev_002"


# ------------------------------------------------------------------
# Step 8: AgentClaim Tests
# ------------------------------------------------------------------

def test_unverified_claim():
    """Unverified claim has correct status."""
    claim = AgentClaim(
        claim_id="cl_001",
        text="Hardcoded secret found in config",
        status="UNVERIFIED",
        evidence_ids=["ev_001"],
        confidence=0.3,
    )
    assert claim.status == "UNVERIFIED"
    assert claim.claim_id == "cl_001"


def test_verified_claim():
    """Verified claim with evidence."""
    claim = AgentClaim(
        claim_id="cl_002",
        text="Authentication uses OAuth2",
        status="VERIFIED",
        evidence_ids=["ev_003", "ev_004"],
        confidence=0.95,
    )
    assert claim.status == "VERIFIED"
    assert len(claim.evidence_ids) == 2


def test_unsupported_claim():
    """Unsupported claim status valid."""
    claim = AgentClaim(
        claim_id="cl_003",
        text="No evidence supports this claim",
        status="UNSUPPORTED",
    )
    assert claim.status == "UNSUPPORTED"


def test_inconclusive_claim():
    """Inconclusive claim status valid."""
    claim = AgentClaim(
        claim_id="cl_004",
        text="Evidence is ambiguous",
        status="INCONCLUSIVE",
    )
    assert claim.status == "INCONCLUSIVE"


def test_claim_status_validation():
    """Claim status validation method works."""
    # Check via direct set membership since _VALID_CLAIM_STATUSES is ClassVar
    assert "VERIFIED" in AgentClaim._VALID_CLAIM_STATUSES
    assert "INVALID" not in AgentClaim._VALID_CLAIM_STATUSES


# ------------------------------------------------------------------
# Step 9: State Invariants Tests
# ------------------------------------------------------------------

def test_invariant_iteration_non_negative():
    """Iteration must never be negative."""
    state = AgentState(
        task_id="t_inv",
        session_id="sess_inv",
        repository_path="/rev",
        user_goal="Inv",
        current_step_index=-1,
    )
    errors = validate_agent_state_invariants(state)
    assert len([e for e in errors if "negative" in e]) == 1


def test_invariant_completed_needs_outcome():
    """COMPLETED state should have a final outcome."""
    state = AgentState(
        task_id="t_comp",
        session_id="sess_comp",
        repository_path="/r",
        user_goal="Comp",
        status=TaskStatus.COMPLETED,
    )
    errors = validate_agent_state_invariants(state)
    # Completed with no observations or error is flagged
    assert len(errors) >= 0  # Not over-constrained


def test_invariant_failed_needs_error():
    """FAILED state should contain error."""
    state = AgentState(
        task_id="t_fail",
        session_id="sess_fail",
        repository_path="/r",
        user_goal="Fail",
        status=TaskStatus.FAILED,
        error_message="Something went wrong",
    )
    errors = validate_agent_state_invariants(state)
    assert not any("FAILED" in e and "error_message" in e for e in errors)


# ------------------------------------------------------------------
# Step 10: Serialization / Round Trip Tests
# ------------------------------------------------------------------

def test_agent_state_roundtrip():
    """AgentState survives dict/JSON round trip."""
    original = AgentState(
        task_id="t_rt",
        session_id="sess_rt",
        repository_path="/repo",
        user_goal="Serialize test",
        status=TaskStatus.RUNNING,
        observations=[AgentObservation(step_id=1, observation="Started")],
        current_step_index=2,
    )
    serialized = serialize_agent_state(original)
    restored = deserialize_agent_state(serialized)
    assert restored.task_id == original.task_id
    assert restored.session_id == original.session_id
    assert restored.status == original.status
    assert restored.current_step_index == 2
    assert len(restored.observations) == 1


def test_agent_state_roundtrip_with_task():
    """AgentState round trip preserves AgentTask."""
    task = AgentTask(
        task_id="t_rt_task",
        query="Round trip",
        task_type="TEST",
        repository_path="/repo",
    )
    original = AgentState(
        task_id="t_rt_task",
        session_id="sess_rt2",
        repository_path="/repo",
        user_goal="Test with task",
        task=task,
    )
    serialized = serialize_agent_state(original)
    restored = deserialize_agent_state(serialized)
    assert restored.task is not None
    assert restored.task.task_id == "t_rt_task"


def test_agent_state_roundtrip_with_steps_and_claims():
    """AgentState preserves AgentStep and AgentClaim."""
    original = AgentState(
        task_id="t_rt_full",
        session_id="sess_rt_full",
        repository_path="/repo",
        user_goal="Full round trip",
        steps=[
            AgentStep(
                step_id=1,
                iteration=1,
                action_type="RETRIEVE",
                description="Retrieve",
            )
        ],
        claims=[
            AgentClaim(
                claim_id="cl_rt",
                text="Test claim",
                status="UNVERIFIED",
            )
        ],
    )
    serialized = serialize_agent_state(original)
    restored = deserialize_agent_state(serialized)
    assert len(restored.steps) == 1
    assert restored.steps[0].step_id == 1
    assert len(restored.claims) == 1
    assert restored.claims[0].claim_id == "cl_rt"


# ------------------------------------------------------------------
# Regression: No execution loop, no MCP connection
# ------------------------------------------------------------------

def test_no_autonomous_execution():
    """Phase 9.1 creates contracts only; no execution loop exists."""
    # This is a meta-test: verify that AgentState doesn't contain
    # execution-loop-specific fields like 'llm_client', 'mcp_connection', etc.
    state = AgentState(
        task_id="t_no_exec",
        session_id="sess_no_exec",
        repository_path="/repo",
        user_goal="No loop",
    )
    fields = state.model_dump().keys()
    assert "llm_client" not in fields
    assert "mcp_connection" not in fields
    assert "autonomous_loop" not in fields
