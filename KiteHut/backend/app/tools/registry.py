"""
Tool Registry for RepoLens Agent.

Manages tool registration, LLM tool schemas generation, permission enforcement,
and tool execution dispatching.
"""

import logging
import uuid
from typing import Any, Dict, List, Optional

from app.agent.permissions.manager import PermissionManager
from app.agent.permissions.policies import PermissionRequest
from app.agent.state.agent_state import ToolResult
from app.tools.base import BaseTool
from app.tools.file_tools import (
    DeleteFileTool,
    EditFileTool,
    ReadFileTool,
    SearchCodeTool,
    SearchFilesTool,
    WriteFileTool,
)
from app.tools.git_tools import (
    GitBranchTool,
    GitCheckoutTool,
    GitCommitTool,
    GitDiffTool,
    GitLogTool,
    GitStatusTool,
)
from app.tools.phase2_tools import (
    ListFilesTool,
    FindSymbolTool,
    GetRepoStructureTool,
    GetDependenciesTool,
    GetGitDiffTool,
    GetGitLogTool,
    RunAnalysisTool,
)
from app.tools.terminal_tools import (
    RunCommandTool,
    RunLinterTool,
    RunTestsTool,
    RunTypecheckTool,
)

logger = logging.getLogger("repolens.tools.registry")


class ToolRegistry:
    """Central registry of all tools callable by the Agent."""

    def __init__(self):
        self._tools: Dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        """Register a tool instance."""
        self._tools[tool.name] = tool
        logger.debug("Registered tool: %s (%s, %s)", tool.name, tool.permission_type, tool.risk_level)

    def get(self, name: str) -> Optional[BaseTool]:
        """Get a tool by name."""
        return self._tools.get(name)

    def list_tools(self) -> List[BaseTool]:
        """List all registered tools."""
        return list(self._tools.values())

    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        """Return JSON Schema tool specifications for LLM tool/function calling."""
        return [tool.to_tool_spec() for tool in self._tools.values()]

    def execute(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        repository_path: str,
        permission_manager: Optional[PermissionManager] = None,
        task_id: str = "default_task",
        call_id: Optional[str] = None,
    ) -> ToolResult:
        """
        Execute a tool after validating permissions and sandbox boundaries.
        """
        cid = call_id or f"call_{uuid.uuid4().hex[:8]}"
        tool = self.get(tool_name)

        if not tool:
            return ToolResult(
                call_id=cid,
                tool_name=tool_name,
                success=False,
                error=f"Tool not found: '{tool_name}'. Available tools: {list(self._tools.keys())}",
            )

        # Ensure repository_path is injected if needed
        exec_args = dict(arguments)
        if "repository_path" not in exec_args:
            exec_args["repository_path"] = repository_path

        # Permission check
        if permission_manager:
            req = PermissionRequest(
                request_id=f"req_{uuid.uuid4().hex[:8]}",
                task_id=task_id,
                permission_type=tool.permission_type,
                risk_level=tool.risk_level,
                tool_name=tool.name,
                description=f"Execute {tool.name} with arguments: {arguments}",
                arguments=exec_args,
                repository_path=repository_path,
            )

            is_allowed = permission_manager.check_permission(req)
            if not is_allowed:
                return ToolResult(
                    call_id=cid,
                    tool_name=tool_name,
                    success=False,
                    error=f"Permission denied: action '{tool_name}' requires approval (risk: {tool.risk_level}).",
                )

        return tool.execute(call_id=cid, **exec_args)


def create_default_tool_registry() -> ToolRegistry:
    """Factory that creates and populates a ToolRegistry with all standard tools."""
    registry = ToolRegistry()

    # File tools
    registry.register(ReadFileTool())
    registry.register(WriteFileTool())
    registry.register(EditFileTool())
    registry.register(DeleteFileTool())
    registry.register(SearchFilesTool())
    registry.register(SearchCodeTool())
    registry.register(ListFilesTool())

    # Terminal & test tools
    registry.register(RunCommandTool())
    registry.register(RunTestsTool())
    registry.register(RunLinterTool())
    registry.register(RunTypecheckTool())

    # Git tools
    registry.register(GitStatusTool())
    registry.register(GitDiffTool())
    registry.register(GitLogTool())
    registry.register(GitBranchTool())
    registry.register(GitCommitTool())
    registry.register(GitCheckoutTool())

    # PRD-named Phase 2 tools
    registry.register(FindSymbolTool())
    registry.register(GetRepoStructureTool())
    registry.register(GetDependenciesTool())
    registry.register(GetGitDiffTool())
    registry.register(GetGitLogTool())
    registry.register(RunAnalysisTool())

    return registry
