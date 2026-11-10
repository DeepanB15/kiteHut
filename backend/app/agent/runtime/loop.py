"""
Interactive Execution Loop for RepoLens Agent.

Implements the autonomous reasoning, tool dispatching, verification, and recovery cycle:
Observe -> Understand -> Plan -> Act -> Test -> Verify -> Report -> Repeat
"""

from datetime import datetime, timezone
import json
import logging
import time
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING

from app.agent.context.manager import AgentContextManager
from app.agent.memory.task_memory import TaskMemory
from app.agent.permissions.manager import PermissionManager
from app.agent.planner.task_planner import TaskPlanner
from app.agent.state.agent_state import (
    AgentObservation,
    AgentState,
    Plan,
    PlanStep,
    StepStatus,
    TaskStatus,
    ToolResult,
)
from app.llm.base import BaseLLMProvider

if TYPE_CHECKING:  # pragma: no cover
    # Deferred: importing registry at runtime would create a cycle
    # (agent.__init__ -> runtime.core -> loop -> registry -> tools.base -> agent.permissions -> agent.__init__)
    from app.tools.registry import ToolRegistry

logger = logging.getLogger("repolens.agent.runtime.loop")


class AgentLoop:
    """
    Drives execution of a single task through planning, tool invocations,
    permission checks, verification, and dynamic replanning.
    """

    def __init__(
        self,
        tools: "ToolRegistry",
        permissions: PermissionManager,
        context_mgr: AgentContextManager,
        planner: TaskPlanner,
        memory: TaskMemory,
        llm: Optional[BaseLLMProvider] = None,
        event_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None,
        max_retries: int = 3,
    ):
        self.tools = tools
        self.permissions = permissions
        self.context_mgr = context_mgr
        self.planner = planner
        self.memory = memory
        self.llm = llm
        self.event_callback = event_callback or (lambda evt, data: None)
        self.max_retries = max_retries
        self._retry_count = 0

    def run(self, state: AgentState) -> AgentState:
        """
        Execute the agent task loop until completion, failure, or awaiting user approval.
        """
        state.status = TaskStatus.PLANNING
        state.updated_at = datetime.now(timezone.utc)
        self._emit("task_planning", {"task_id": state.task_id, "goal": state.user_goal})

        # Generate plan if not already present
        if not state.plan or len(state.plan.steps) == 0:
            state.plan = self.planner.create_plan(
                task_id=state.task_id,
                goal=state.user_goal,
                repository_path=state.repository_path,
            )
            self._emit("plan_created", {
                "task_id": state.task_id,
                "steps": [s.model_dump() for s in state.plan.steps],
            })

        state.status = TaskStatus.RUNNING
        state.updated_at = datetime.now(timezone.utc)

        while state.current_step_index < len(state.plan.steps):
            if state.status == TaskStatus.CANCELLED:
                self._emit("task_cancelled", {"task_id": state.task_id})
                return state

            current_step = state.plan.steps[state.current_step_index]
            current_step.status = StepStatus.RUNNING
            self._emit("step_started", {"task_id": state.task_id, "step": current_step.model_dump()})

            step_success = self._execute_step(state, current_step)

            if state.status == TaskStatus.WAITING_APPROVAL:
                # Paused waiting for user approval decision
                return state

            if not step_success:
                self._retry_count += 1
                if self._retry_count > self.max_retries:
                    state.status = TaskStatus.FAILED
                    state.error_message = f"Max retries exceeded on step {current_step.step_id}: {current_step.error}"
                    current_step.status = StepStatus.FAILED
                    state.updated_at = datetime.now(timezone.utc)
                    self._emit("task_failed", {"task_id": state.task_id, "error": state.error_message})
                    return state

                # Dynamic replanning on step failure
                logger.warning("Step %d failed. Initiating dynamic replan.", current_step.step_id)
                state.plan = self.planner.replan_on_failure(
                    plan=state.plan,
                    failed_step=current_step,
                    error_message=current_step.error or "Unknown failure",
                )
                state.current_step_index += 1
                self._emit("plan_updated", {
                    "task_id": state.task_id,
                    "steps": [s.model_dump() for s in state.plan.steps],
                })
                continue

            # Step completed successfully
            current_step.status = StepStatus.COMPLETED
            state.current_step_index += 1
            state.updated_at = datetime.now(timezone.utc)
            self._emit("step_completed", {"task_id": state.task_id, "step": current_step.model_dump()})

        state.status = TaskStatus.COMPLETED
        state.updated_at = datetime.now(timezone.utc)
        self._emit("task_completed", {"task_id": state.task_id})
        return state

    def resume_after_approval(self, state: AgentState, approved: bool) -> AgentState:
        """
        Resumes execution when a pending approval decision is received.
        """
        if not approved:
            # User denied the action -> replan or fail gracefully
            current_step = state.plan.steps[state.current_step_index] if state.plan else None
            if current_step:
                current_step.status = StepStatus.SKIPPED
                current_step.error = "Operation was denied by user."
            state.status = TaskStatus.RUNNING
            state.current_step_index += 1
            return self.run(state)

        state.status = TaskStatus.RUNNING
        return self.run(state)

    def _execute_step(self, state: AgentState, step: PlanStep) -> bool:
        """
        Execute a single plan step, invoking the assigned tool or reasoning LLM.
        """
        # Determine tool name and arguments
        tool_name = step.tool_name
        tool_args = dict(step.arguments)

        # If step has no explicit tool name but LLM is available, consult LLM
        if not tool_name and self.llm and self.llm.is_available():
            prompt = self.context_mgr.assemble_step_prompt(
                state=state,
                step_description=step.description,
                expected_output=step.expected_output,
                available_tools=self.tools.get_tool_schemas(),
            )
            response = self.llm.generate(prompt=prompt)
            tool_call = self._parse_llm_tool_call(response)
            if tool_call:
                tool_name = tool_call.get("tool")
                tool_args = tool_call.get("arguments", {})

        # If no tool to run, treat step as pure observation/synthesis
        if not tool_name:
            obs = AgentObservation(
                step_id=step.step_id,
                observation=f"Completed: {step.description}",
            )
            state.observations.append(obs)
            return True

        # Pre-execution rollback snapshot for modifying file tools
        if tool_name in ("write_file", "edit_file", "delete_file"):
            target_path = tool_args.get("path") or tool_args.get("file_path")
            if target_path:
                self.memory.record_file_snapshot(target_path)

        # Execute tool through ToolRegistry
        result: ToolResult = self.tools.execute(
            tool_name=tool_name,
            arguments=tool_args,
            repository_path=state.repository_path,
            permission_manager=self.permissions,
            task_id=state.task_id,
        )

        step.result = result
        state.tool_history.append(result)

        if not result.success:
            if "requires approval" in (result.error or "").lower() or "permission denied" in (result.error or "").lower():
                state.status = TaskStatus.WAITING_APPROVAL
                state.updated_at = datetime.now(timezone.utc)
                self._emit("approval_required", {
                    "task_id": state.task_id,
                    "tool_name": tool_name,
                    "arguments": tool_args,
                    "step_id": step.step_id,
                })
                return False

            step.error = result.error
            return False

        # Record observation
        state.observations.append(
            AgentObservation(
                step_id=step.step_id,
                observation=f"Tool {tool_name} executed successfully. Output summary: {(result.output or '')[:200]}",
            )
        )
        return True

    def _parse_llm_tool_call(self, text: str) -> Optional[Dict[str, Any]]:
        """Parse structured tool call JSON blocks from model response."""
        try:
            if "```json" in text:
                block = text.split("```json")[1].split("```")[0].strip()
                data = json.loads(block)
                if "tool" in data:
                    return data
            elif text.strip().startswith("{") and text.strip().endswith("}"):
                data = json.loads(text.strip())
                if "tool" in data:
                    return data
        except Exception:
            return None
        return None

    def _emit(self, event_type: str, data: Dict[str, Any]) -> None:
        try:
            self.event_callback(event_type, data)
        except Exception as error:
            logger.error("Event callback error on %s: %s", event_type, error)
