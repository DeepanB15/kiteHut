"""
Tool Executor — Phase 9.3.

Controlled execution boundary: ToolSelection -> registry validation ->
approval check -> existing registry.execute() -> ToolResult -> AgentState update.
No arbitrary execution. No autonomous loop.
"""

import uuid
from typing import Optional, Dict, Any

from app.agent.state.agent_state import AgentState, AgentTask, AgentObservation, ToolResult
from app.agent.router.tool_router_contracts import ToolSelection, ToolCategory, get_registry, ToolCapability
from app.agent.permissions.manager import PermissionManager
from app.agent.permissions.policies import PermissionType, RiskLevel, PermissionRequest, DecisionType
from app.agent.router.router import AgentRouter

# Status for execution outcomes
from enum import Enum


class ExecutionStatus(str, Enum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    REJECTED = "REJECTED"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"


class ToolExecutor:
    """Controlled execution boundary: validates, approves, executes, observes."""

    def __init__(
        self,
        registry: Optional[Dict[str, ToolCapability]] = None,
        permission_manager: Optional[PermissionManager] = None,
    ):
        self.registry = registry or get_registry()
        self.permission_manager = permission_manager or PermissionManager(auto_allow_safe=True)

    def execute(
        self,
        selection: ToolSelection,
        arguments: Optional[Dict[str, Any]] = None,
        repository_path: str = ".",
        task_id: str = "",
        state: Optional[AgentState] = None,
        approval_granted: bool = False,
    ) -> ToolResult:
        """Execute a ToolSelection through the controlled boundary."""
        args = dict(arguments) if arguments else {}

        # 1. Registry validation: unknown tool rejected
        tool_name = selection.primary_tool.tool_name
        if not tool_name:
            return ToolResult(
                call_id=f"call_{uuid.uuid4().hex[:8]}",
                tool_name="",
                success=False,
                error="REJECTED: tool selection has no registered tool name",
            )

        if tool_name not in self.registry:
            return ToolResult(
                call_id=f"call_{uuid.uuid4().hex[:8]}",
                tool_name=tool_name,
                success=False,
                error=f"REJECTED: unknown tool '{tool_name}' not in registry",
            )

        capability = self.registry[tool_name]

        # 2. Approval boundary
        requires_approval = capability.requires_approval or not capability.read_only
        if requires_approval and not approval_granted:
            # Check permission manager explicitly
            # Build minimal PermissionRequest from capability metadata
            req = PermissionRequest(
                request_id=f"req_{uuid.uuid4().hex[:8]}",
                task_id=task_id or "unknown",
                permission_type=PermissionType.READ if capability.read_only else PermissionType.EXECUTE,
                risk_level=RiskLevel.SAFE if capability.read_only else RiskLevel.APPROVAL_REQUIRED,
                tool_name=tool_name,
                description=f"Execute {tool_name}",
                arguments=args,
                repository_path=repository_path,
            )
            allowed = self.permission_manager.check_permission(req)
            if not allowed:
                return ToolResult(
                    call_id=f"call_{uuid.uuid4().hex[:8]}",
                    tool_name=tool_name,
                    success=False,
                    error="APPROVAL_REQUIRED: privileged/mutating operation requires approval",
                )

        # 3. Argument validation (structural, not arbitrary shell)
        # Ensure repository_path is present for tools that expect it
        args.setdefault("repository_path", repository_path)

        # 4. Execute through existing registry (NOT arbitrary subprocess)
        from app.tools.registry import create_default_tool_registry
        real_registry = create_default_tool_registry()
        # Resolve to real registry for execution; fall back if not present
        if real_registry.get(tool_name):
            result = real_registry.execute(
                tool_name=tool_name,
                arguments=args,
                repository_path=repository_path,
                permission_manager=self.permission_manager,
                task_id=task_id,
            )
        else:
            # If real registry doesn't have it (shouldn't happen with 23 names), reject
            return ToolResult(
                call_id=f"call_{uuid.uuid4().hex[:8]}",
                tool_name=tool_name,
                success=False,
                error=f"REJECTED: tool '{tool_name}' not available in execution registry",
            )

        # 5. Update AgentState if provided (read-only safe path)
        if state is not None and result.success:
            # Add observation
            observation = AgentObservation(
                step_id=len(state.observations) + 1,
                observation=f"Executed {tool_name}: {str(result.output)[:200] if result.output else 'ok'}",
            )
            state.observations.append(observation)
            # Add tool history
            state.tool_history.append(result)
            # Add step record (Phase 9.1 AgentStep)
            from app.agent.state.agent_state import AgentStep, StepStatus
            step = AgentStep(
                step_id=len(state.observations),
                iteration=1,
                action_type="OBSERVE" if result.success else "VERIFY",
                description=f"Tool execution: {tool_name}",
                status=StepStatus.COMPLETED if result.success else StepStatus.FAILED,
                output={"result_success": result.success, "output_preview": (result.output or "")[:200]},
            )
            if not hasattr(state, 'steps') or state.steps is None:
                # Defensive: ensure steps list exists (should by Pydantic)
                pass
            state.steps.append(step)
            # Add final_answer placeholder for completed steps
            if result.success:
                state.final_answer = result.output

        return result

    def execute_read_only(
        self,
        selection: ToolSelection,
        arguments: Optional[Dict[str, Any]] = None,
        repository_path: str = ".",
        task_id: str = "",
        state: Optional[AgentState] = None,
    ) -> ToolResult:
        """Execute a read-only selection (approval not needed by design)."""
        return self.execute(
            selection=selection,
            arguments=arguments,
            repository_path=repository_path,
            task_id=task_id,
            state=state,
            approval_granted=True,
        )
