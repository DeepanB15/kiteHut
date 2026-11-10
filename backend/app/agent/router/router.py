"""
Agent Router — Phase 9.2.

Deterministic routing logic: AgentTask -> ToolSelection.
Side-effect free. No MCP execution.
"""

import uuid
from typing import Optional, Dict

from app.agent.state.agent_state import AgentTask, AgentStatus
from app.agent.router.tool_router_contracts import (
    ToolSelection, ToolDecision, ToolCategory, ToolCapability, get_registry
)


class AgentRouter:
    """Deterministic router: AgentTask -> ToolSelection."""

    def __init__(self, registry: Optional[Dict[str, ToolCapability]] = None):
        self.registry = registry or get_registry()

    def route(self, task: AgentTask) -> ToolSelection:
        """Route a task to a tool decision. Side-effect free."""
        decision_id = str(uuid.uuid4())[:8]

        if not task.task_type:
            return ToolSelection(
                primary_tool=ToolDecision(
                    decision_id=decision_id,
                    task_id=task.task_id,
                    tool_name="",
                    category=ToolCategory.RETRIEVAL,
                    reason="Task has no type; clarification required",
                    confidence=0.0,
                    requires_confirmation=False,
                ),
                ambiguity=True,
                clarification_needed=True,
            )

        category_map = {
            "QUESTION": ToolCategory.RETRIEVAL,
            "REVIEW": ToolCategory.REVIEW,
            "INVESTIGATE": ToolCategory.RETRIEVAL,
            "EXPLAIN": ToolCategory.RETRIEVAL,
            "TEST": ToolCategory.TESTING,
            "FIX": ToolCategory.CODE,
        }
        base_category = category_map.get(task.task_type, ToolCategory.RETRIEVAL)
        query_lower = (task.query or "").lower()

        selected_name = ""
        reason = ""
        confidence = 0.5

        if "git" in query_lower or "commit" in query_lower or "branch" in query_lower:
            if "diff" in query_lower:
                selected_name = "get_git_diff" if "get_git_diff" in self.registry else "git_diff"
                reason = "Query references git diff"
            elif "log" in query_lower:
                selected_name = "get_git_log" if "get_git_log" in self.registry else "git_log"
                reason = "Query references git log"
            elif "branch" in query_lower:
                selected_name = "git_branch"
                reason = "Query references branch"
            else:
                selected_name = "git_status"
                reason = "Query references git"
            confidence = 0.8
        elif "test" in query_lower or "tests" in query_lower:
            selected_name = "run_tests"
            reason = "Query references testing"
            confidence = 0.85
        elif "auth" in query_lower or "authentication" in query_lower:
            selected_name = "search_code"
            reason = "Security/auth query -> code retrieval"
            confidence = 0.75
        elif "dependency" in query_lower or "dependencies" in query_lower:
            selected_name = "get_dependencies"
            reason = "Dependency analysis query"
            confidence = 0.85
        elif "explain" in query_lower or "what is" in query_lower or "where" in query_lower:
            selected_name = "search_code"
            reason = "Explanation/retrieval query"
            confidence = 0.7
        elif "security" in query_lower:
            selected_name = "run_analysis"
            reason = "Security review -> analysis"
            confidence = 0.75
        elif "review" in query_lower:
            selected_name = "run_analysis"
            reason = "Review task -> analysis"
            confidence = 0.7
        elif "structure" in query_lower or "repo" in query_lower:
            selected_name = "get_repo_structure"
            reason = "Repository structure query"
            confidence = 0.8
        else:
            if base_category == ToolCategory.RETRIEVAL:
                selected_name = "search_code"
                reason = f"Default retrieval for task type {task.task_type}"
            elif base_category == ToolCategory.TESTING:
                selected_name = "run_tests"
                reason = f"Default testing for task type {task.task_type}"
            elif base_category == ToolCategory.CODE:
                selected_name = "read_file"
                reason = f"Default code read for task type {task.task_type}"
            elif base_category == ToolCategory.REVIEW:
                selected_name = "run_analysis"
                reason = f"Default review/analysis for task type {task.task_type}"
            else:
                selected_name = "search_code"
                reason = f"Default fallback for task type {task.task_type}"
            confidence = 0.6

        if not selected_name or selected_name not in self.registry:
            return ToolSelection(
                primary_tool=ToolDecision(
                    decision_id=decision_id,
                    task_id=task.task_id,
                    tool_name="",
                    category=base_category,
                    reason="No registered capability matched; clarification required",
                    confidence=0.0,
                    requires_confirmation=False,
                ),
                ambiguity=True,
                clarification_needed=True,
            )

        capability = self.registry[selected_name]
        requires_confirmation = capability.requires_approval or not capability.read_only

        primary = ToolDecision(
            decision_id=decision_id,
            task_id=task.task_id,
            tool_name=selected_name,
            category=capability.category,
            reason=reason,
            confidence=confidence,
            requires_confirmation=requires_confirmation,
        )

        return ToolSelection(
            primary_tool=primary,
            ambiguity=False,
            clarification_needed=False,
        )
