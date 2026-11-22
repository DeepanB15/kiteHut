"""
Agent Router — Phase 9.2.

Deterministic routing logic: AgentTask -> ToolSelection.
Side-effect free. No MCP execution.
"""

import re
import uuid
from typing import Any, Dict, List, Optional

from app.agent.state.agent_state import AgentTask, AgentStatus
from app.agent.router.tool_router_contracts import (
    ToolSelection, ToolDecision, ToolCategory, ToolCapability, get_registry
)


_EXTRACTED_ARGUMENT_PATTERNS: Dict[str, List[str]] = {
    "symbol": [
        r"who\s+calls",
        r"callers?\s+of",
        r"callees?\s+of",
        r"symbol\s+(?:named\s+)?",
        r"changing",
    ],
    "path": [
        r"dependents?\s+of",
        r"imports?\s+(?:for|of)",
        r"file\s+",
    ],
    "target": [
        r"impact\s+of\s+(?:changing|modifying|editing)",
        r"impact\s+of",
        r"affected\s+by",
    ],
}

_GRAPH_ARGUMENT_KEYS = {
    "graph_find_symbol": "query",
    "graph_callers": "symbol",
    "graph_callees": "symbol",
    "graph_imports": "path",
    "graph_dependents": "path",
    "graph_impact": "target",
    "graph_context": "query",
    "verify_claim": "claim",
}


_FIND_SYMBOL_PATTERNS = [
    r"(?:find|locate|lookup|look\s+up)\s+(?:the\s+)?(?:symbol|function|class|method|module)?\s*",
    r"where\s+is\s+(?:the\s+)?(?:symbol|function|class|method|module)?\s*",
    r"symbol\s+(?:named\s+)?",
]


def _extract_symbol_query(query: str) -> Optional[str]:
    """Extract the symbol name a lookup query refers to."""
    for pattern in _FIND_SYMBOL_PATTERNS:
        match = re.search(pattern + r"([A-Za-z_][\w.]*)", query, re.IGNORECASE)
        if match:
            value = match.group(1).rstrip("?.!,;:")
            if value:
                return value
    return None


def _extract_argument(query: str, patterns: List[str]) -> Optional[str]:
    for pattern in patterns:
        match = re.search(
            pattern + r"\s+(?:the\s+|symbol\s+|file\s+)?([A-Za-z_][\w./\\-]*)",
            query,
            re.IGNORECASE,
        )
        if match:
            value = match.group(1).rstrip("?.!,;:")
            if value:
                return value
    return None


def _suggest_arguments(tool_name: str, query: str) -> Dict[str, Any]:
    """Derive deterministic tool arguments from the task query.

    Only the graph/evidence tools are covered; existing tools keep their
    current argument handling.  Suggestions are hints that the executor merges
    with explicitly supplied arguments.
    """
    key = _GRAPH_ARGUMENT_KEYS.get(tool_name)
    if key is None or not query:
        return {}
    if tool_name in {"graph_context", "verify_claim"}:
        return {key: query.strip()}
    if tool_name == "graph_find_symbol":
        value = _extract_symbol_query(query)
        return {key: value} if value else {}
    value = _extract_argument(query, _EXTRACTED_ARGUMENT_PATTERNS.get(key, []))
    return {key: value} if value else {}


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
        elif (
            "caller" in query_lower
            or "called by" in query_lower
            or "who calls" in query_lower
        ):
            selected_name = "graph_callers"
            reason = "Query references static callers"
            confidence = 0.8
        elif "callee" in query_lower or "calls into" in query_lower:
            selected_name = "graph_callees"
            reason = "Query references static callees"
            confidence = 0.8
        elif (
            "dependents" in query_lower
            or "who imports" in query_lower
            or "impact" in query_lower
            or "affected" in query_lower
        ):
            if "impact" in query_lower or "affected" in query_lower:
                selected_name = "graph_impact"
                reason = "Query references dependency/impact navigation"
            else:
                selected_name = "graph_dependents"
                reason = "Query references files that import another file"
            confidence = 0.8
        elif " import" in f" {query_lower}":
            selected_name = "graph_imports"
            reason = "Query references file imports"
            confidence = 0.75
        elif "code graph" in query_lower and "context" in query_lower:
            selected_name = "graph_context"
            reason = "Query explicitly requests graph-guided context"
            confidence = 0.75
        elif "verify" in query_lower and (
            "claim" in query_lower or "evidence" in query_lower
        ):
            selected_name = "verify_claim"
            reason = "Query asks to verify a claim with evidence"
            confidence = 0.8
        elif "symbol" in query_lower and (
            "find" in query_lower
            or "lookup" in query_lower
            or "locate" in query_lower
            or "where" in query_lower
        ):
            selected_name = "graph_find_symbol"
            reason = "Query asks to locate a symbol"
            confidence = 0.75
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
            suggested_arguments=_suggest_arguments(selected_name, task.query or ""),
        )

        return ToolSelection(
            primary_tool=primary,
            ambiguity=False,
            clarification_needed=False,
        )
