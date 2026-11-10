"""
Phase 9.4 — Multi-Step Evidence-Grounded Agent Loop.

Bounded, synchronous, deterministic, read-only investigation.
Uses existing AgentRouter, ToolExecutor, AgentState.
No LLM planner. No autonomous mutation. Hard max_steps.
"""

from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

from app.agent.state.agent_state import AgentTask, AgentState, AgentObservation, AgentStep, StepStatus, AgentStatus
from app.agent.router.router import AgentRouter
from app.agent.router.tool_executor import ToolExecutor
from app.agent.router.tool_router_contracts import get_registry, ToolCategory


class EvidenceSufficiencyPolicy:
    """Deterministic evidence sufficiency check."""

    def is_sufficient(self, task: AgentTask, observations: List[AgentObservation], steps_taken: int) -> bool:
        # At least one successful observation with non-empty content is baseline
        meaningful = [o for o in observations if o.observation and len(o.observation) > 5]
        if len(meaningful) >= 1:
            # For stronger tasks (investigate/review/explain) require corroboration
            if task.task_type in ("INVESTIGATE", "REVIEW", "EXPLAIN"):
                return len(meaningful) >= 2
            return True
        return False


class EvidenceCollector:
    """Lightweight accumulation of observations/evidence from execution."""

    def collect(self, result, state: AgentState):
        # Already handled by ToolExecutor updating state; this is a hook
        pass


class AgentLoop94:
    """Bounded evidence-grounded loop for Phase 9.4."""

    def __init__(
        self,
        max_steps: int = 5,
        router: Optional[AgentRouter] = None,
        executor: Optional[ToolExecutor] = None,
    ):
        self.max_steps = min(max_steps, 5)
        self.router = router or AgentRouter()
        self.executor = executor or ToolExecutor()
        self.policy = EvidenceSufficiencyPolicy()

    def run(self, task: AgentTask, repository_path: str = ".") -> AgentState:
        state = AgentState(
            task_id=task.task_id,
            session_id=f"sess_{task.task_id}",
            repository_path=repository_path,
            user_goal=task.query,
            task=task,
        )

        for step_index in range(self.max_steps):
            state.current_step_index = step_index
            state.status = AgentStatus.EXECUTING  # Use existing enum

            # Route
            selection = self.router.route(task)

            # If ambiguous / no tool, stop with clarification
            if selection.ambiguity or selection.clarification_needed or not selection.primary_tool.tool_name:
                state.status = AgentStatus.FAILED
                state.error_message = "Ambiguous task; clarification required"
                state.observations.append(AgentObservation(
                    step_id=step_index + 1,
                    observation="Ambiguous: no confident tool selection",
                ))
                return state

            # Execute read-only (approval not needed for safe read-only)
            result = self.executor.execute_read_only(
                selection=selection,
                repository_path=repository_path,
                task_id=task.task_id,
                state=state,
            )

            # Capture observation (ToolExecutor updates state; enforce here)
            if result.success:
                # Evidence accumulated via ToolExecutor; sufficiency check
                if self.policy.is_sufficient(task, state.observations, step_index + 1):
                    state.status = AgentStatus.COMPLETED
                    state.final_answer = f"Grounded result after {step_index + 1} step(s). Evidence: {len(state.observations)} observation(s)."
                    state.updated_at = datetime.now(timezone.utc)
                    return state
                else:
                    # Continue to next bounded step
                    continue
            else:
                # Failure preserved; stop (do not invent success)
                state.status = AgentStatus.FAILED
                state.error_message = result.error or "Execution failed"
                state.observations.append(AgentObservation(
                    step_id=step_index + 1,
                    observation=f"Failed execution: {result.error}",
                ))
                return state

        # Max steps reached
        state.updated_at = datetime.now(timezone.utc)
        if self.policy.is_sufficient(task, state.observations, self.max_steps):
            state.status = AgentStatus.COMPLETED
            state.final_answer = f"Grounded after max steps ({self.max_steps}). Evidence: {len(state.observations)} observation(s)."
        else:
            state.status = AgentStatus.FAILED
            state.error_message = "Insufficient evidence after maximum steps"
            state.final_answer = "INSUFFICIENT_EVIDENCE"
        return state
