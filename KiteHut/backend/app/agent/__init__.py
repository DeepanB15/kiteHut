"""
Agent package for RepoLens.

Provides the autonomous AI engineering agent core, runtime loop,
permission management, task planning, and contextual execution system.
"""

from app.agent.context.manager import AgentContextManager
from app.agent.memory.task_memory import TaskMemory
from app.agent.permissions.manager import PermissionManager
from app.agent.permissions.policies import (
    DecisionType,
    PermissionRequest,
    PermissionType,
    RiskLevel,
)
from app.agent.planner.task_planner import TaskPlanner
from app.agent.runtime.core import AgentCore, get_agent_core
from app.agent.runtime.loop import AgentLoop
from app.agent.state.agent_state import (
    AgentObservation,
    AgentState,
    AgentStep,
    AgentStatus,
    AgentTask,
    AgentClaim,
    EvidenceReference,
    Plan,
    PlanStep,
    StepStatus,
    TaskStatus,
    ToolCall,
    ToolResult,
)

__all__ = [
    "AgentContextManager",
    "AgentCore",
    "AgentLoop",
    "AgentObservation",
    "AgentState",
    "AgentStep",
    "AgentStatus",
    "AgentTask",
    "AgentClaim",
    "EvidenceReference",
    "DecisionType",
    "PermissionManager",
    "PermissionRequest",
    "PermissionType",
    "Plan",
    "PlanStep",
    "RiskLevel",
    "StepStatus",
    "TaskMemory",
    "TaskPlanner",
    "TaskStatus",
    "ToolCall",
    "ToolResult",
    "get_agent_core",
]
