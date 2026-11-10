"""
Agent Core Facade for RepoLens.

Unified engine interface serving CLI, Chat, Web Dashboard, and API integrations.
Manages task lifecycles, permission managers, tool registries, and execution loops.
"""

from datetime import datetime, timezone
import logging
from typing import Any, Callable, Dict, List, Optional
import uuid

from app.agent.context.manager import AgentContextManager
from app.agent.memory.task_memory import TaskMemory
# Import deferred to avoid circular dependency:
# agent.__init__ -> core -> registry -> base -> agent.permissions -> agent.__init__
from app.agent.permissions.manager import PermissionManager
from app.agent.permissions.policies import DecisionType, PermissionRequest
from app.agent.planner.task_planner import TaskPlanner
from app.agent.runtime.loop import AgentLoop
from app.agent.state.agent_state import AgentState, TaskStatus
from app.llm.base import BaseLLMProvider
from app.llm.factory import create_llm_provider

from typing import TYPE_CHECKING
if TYPE_CHECKING:  # pragma: no cover
    from app.tools.registry import ToolRegistry, create_default_tool_registry

logger = logging.getLogger("repolens.agent.core")


_UNSET = object()


class AgentCore:
    """
    Unified Agent Core orchestrator.
    """

    def __init__(
        self,
        tool_registry: Optional["ToolRegistry"] = None,
        llm_provider: Any = _UNSET,
    ):
        from app.tools.registry import create_default_tool_registry  # lazy; avoids cycle
        self.tools = tool_registry or create_default_tool_registry()
        if llm_provider is _UNSET:
            try:
                self.llm = create_llm_provider()
            except Exception:
                self.llm = None
        else:
            self.llm = llm_provider

        self.tasks: Dict[str, AgentState] = {}
        self.memories: Dict[str, TaskMemory] = {}
        self.permission_managers: Dict[str, PermissionManager] = {}

    def create_task(
        self,
        repository_path: str,
        user_goal: str,
        session_id: Optional[str] = None,
        approval_callback: Optional[Callable[[PermissionRequest], DecisionType]] = None,
        auto_allow_safe: bool = True,
        auto_allow_all: bool = False,
    ) -> AgentState:
        """Create and initialize a new agent task."""
        task_id = f"task_{uuid.uuid4().hex[:12]}"
        sess_id = session_id or f"sess_{uuid.uuid4().hex[:8]}"

        state = AgentState(
            task_id=task_id,
            session_id=sess_id,
            repository_path=repository_path,
            user_goal=user_goal,
            status=TaskStatus.PENDING,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        self.tasks[task_id] = state
        self.memories[task_id] = TaskMemory(task_id, repository_path)
        self.permission_managers[task_id] = PermissionManager(
            approval_callback=approval_callback,
            auto_allow_safe=auto_allow_safe,
            auto_allow_all=auto_allow_all,
        )

        logger.info("Created agent task: %s (Goal: %s)", task_id, user_goal)
        return state

    def run_task(
        self,
        task_id: str,
        event_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None,
    ) -> AgentState:
        """Run an existing task to completion or next approval boundary."""
        state = self.tasks.get(task_id)
        if not state:
            raise ValueError(f"Task '{task_id}' not found.")

        memory = self.memories[task_id]
        perm_mgr = self.permission_managers[task_id]
        context_mgr = AgentContextManager(repository_path=state.repository_path)
        planner = TaskPlanner(llm_provider=self.llm)

        loop = AgentLoop(
            tools=self.tools,
            permissions=perm_mgr,
            context_mgr=context_mgr,
            planner=planner,
            memory=memory,
            llm=self.llm,
            event_callback=event_callback,
        )

        return loop.run(state)

    def handle_approval(
        self,
        task_id: str,
        decision: DecisionType,
        tool_name: Optional[str] = None,
        event_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None,
    ) -> AgentState:
        """
        Record user approval decision and resume task execution.
        """
        state = self.tasks.get(task_id)
        if not state:
            raise ValueError(f"Task '{task_id}' not found.")

        perm_mgr = self.permission_managers[task_id]
        memory = self.memories[task_id]
        context_mgr = AgentContextManager(repository_path=state.repository_path)
        planner = TaskPlanner(llm_provider=self.llm)

        if decision == DecisionType.ALLOW_FOR_TASK and tool_name:
            perm_mgr.grant_task(task_id, tool_name)
        elif decision == DecisionType.ALLOW_FOR_REPO and tool_name:
            perm_mgr.grant_repo(state.repository_path, tool_name)

        loop = AgentLoop(
            tools=self.tools,
            permissions=perm_mgr,
            context_mgr=context_mgr,
            planner=planner,
            memory=memory,
            llm=self.llm,
            event_callback=event_callback,
        )

        approved = decision != DecisionType.DENY
        return loop.resume_after_approval(state, approved=approved)

    def cancel_task(self, task_id: str) -> bool:
        """Cancel an active task."""
        state = self.tasks.get(task_id)
        if not state:
            return False

        state.status = TaskStatus.CANCELLED
        state.updated_at = datetime.now(timezone.utc)
        return True

    def rollback_task(self, task_id: str) -> List[str]:
        """Rollback all filesystem modifications made during this task."""
        memory = self.memories.get(task_id)
        if not memory:
            return []
        return memory.rollback_all()

    def get_task(self, task_id: str) -> Optional[AgentState]:
        """Get state of a task."""
        return self.tasks.get(task_id)


_GLOBAL_AGENT_CORE: Optional[AgentCore] = None


def get_agent_core() -> AgentCore:
    """Singleton getter for AgentCore."""
    global _GLOBAL_AGENT_CORE
    if _GLOBAL_AGENT_CORE is None:
        _GLOBAL_AGENT_CORE = AgentCore()
    return _GLOBAL_AGENT_CORE
