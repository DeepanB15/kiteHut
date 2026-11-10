"""
Permission Manager for RepoLens.

Enforces security boundaries, checks tool risk policies, and manages scoped grants
(ALLOW_ONCE, ALLOW_FOR_TASK, ALLOW_FOR_REPO, DENY).
"""

import logging
from typing import Callable, Dict, Optional, Set

from app.agent.permissions.policies import (
    DecisionType,
    PermissionRequest,
    RiskLevel,
)

logger = logging.getLogger("repolens.permissions")


class PermissionManager:
    """
    Evaluates permission requests against security policies and grant history.
    """

    def __init__(
        self,
        approval_callback: Optional[Callable[[PermissionRequest], DecisionType]] = None,
        auto_allow_safe: bool = True,
        auto_allow_all: bool = False,
    ):
        self.approval_callback = approval_callback
        self.auto_allow_safe = auto_allow_safe
        self.auto_allow_all = auto_allow_all

        # Scoped permission grants
        self._task_grants: Dict[str, Set[str]] = {}  # task_id -> {tool_name}
        self._repo_grants: Dict[str, Set[str]] = {}  # repo_path -> {tool_name}
        self._denied_requests: Set[str] = set()

    def check_permission(self, request: PermissionRequest) -> bool:
        """
        Check whether a permission request is authorized.
        Returns True if authorized, False otherwise.
        """
        # Testing / fully automated override
        if self.auto_allow_all:
            logger.debug("Auto-allowing action (auto_allow_all=True): %s", request.tool_name)
            return True

        # Safe actions (read_file, git_status, search_code) pass automatically
        if self.auto_allow_safe and request.risk_level == RiskLevel.SAFE:
            logger.debug("Auto-allowing safe tool: %s", request.tool_name)
            return True

        # Check repository-level grants
        repo_tools = self._repo_grants.get(request.repository_path, set())
        if request.tool_name in repo_tools:
            logger.debug("Tool %s granted at repository level", request.tool_name)
            return True

        # Check task-level grants
        task_tools = self._task_grants.get(request.task_id, set())
        if request.tool_name in task_tools:
            logger.debug("Tool %s granted at task level", request.tool_name)
            return True

        # Interactive approval handler
        if self.approval_callback:
            try:
                decision = self.approval_callback(request)
                if decision == DecisionType.ALLOW_ONCE:
                    logger.info("Tool %s approved for one-time execution", request.tool_name)
                    return True
                elif decision == DecisionType.ALLOW_FOR_TASK:
                    self._task_grants.setdefault(request.task_id, set()).add(request.tool_name)
                    logger.info("Tool %s approved for entire task %s", request.tool_name, request.task_id)
                    return True
                elif decision == DecisionType.ALLOW_FOR_REPO:
                    self._repo_grants.setdefault(request.repository_path, set()).add(request.tool_name)
                    logger.info("Tool %s approved for repository %s", request.tool_name, request.repository_path)
                    return True
                else:
                    self._denied_requests.add(request.request_id)
                    logger.warning("Permission denied for %s on task %s", request.tool_name, request.task_id)
                    return False
            except Exception as error:
                logger.error("Error during permission callback: %s", error)
                return False

        logger.warning(
            "Tool %s requires approval (risk: %s), but no callback is configured.",
            request.tool_name,
            request.risk_level,
        )
        return False

    def grant_permission(
        self,
        tool_name: str,
        scope: DecisionType,
        task_id: Optional[str] = None,
        repository_path: Optional[str] = None,
    ) -> None:
        """Manually grant permission for a tool within a specific scope."""
        if scope == DecisionType.ALLOW_FOR_TASK and task_id:
            self._task_grants.setdefault(task_id, set()).add(tool_name)
        elif scope == DecisionType.ALLOW_FOR_REPO and repository_path:
            self._repo_grants.setdefault(repository_path, set()).add(tool_name)

    def revoke_task_grants(self, task_id: str) -> None:
        """Clear all grants for a finished or cancelled task."""
        self._task_grants.pop(task_id, None)

    def revoke_repo_grants(self, repository_path: str) -> None:
        """Clear all grants for a repository."""
        self._repo_grants.pop(repository_path, None)

    def revoke_all(self) -> None:
        """Clear all grants across all scopes."""
        self._task_grants.clear()
        self._repo_grants.clear()
        self._denied_requests.clear()
