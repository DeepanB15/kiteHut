"""
RepoLens MCP Server — Phase 2.

Uses FastMCP (mcp 1.x) to expose all registered agent tools
through a single MCP server endpoint.
"""

import logging
from typing import Any, Dict, List, Optional

from mcp.server.fastmcp import FastMCP

from app.tools.registry import create_default_tool_registry
from app.agent.permissions.manager import PermissionManager

logger = logging.getLogger("repolens.mcp.server")


_JSON_TYPE_MAP = {
    "string": str,
    "integer": int,
    "number": float,
    "boolean": bool,
    "array": list,
    "object": dict,
}


def _json_type_to_python(json_type: Optional[str]):
    """Map a JSON-schema type name to a Python type for MCP signatures."""
    return _JSON_TYPE_MAP.get(json_type or "", Any)


class RepoLensMCPServer:
    """Single MCP server exposing RepoLens agent tool set."""

    def __init__(self, repository_path: Optional[str] = None):
        self.mcp = FastMCP("RepoLens Agent Tools")
        self.repository_path = repository_path or "."
        self.registry = create_default_tool_registry()
        self.permission_manager = PermissionManager()
        self._register_all()

    def _register_all(self):
        """Register every tool in the registry as an MCP tool."""
        for tool in self.registry.list_tools():
            self.mcp.tool()(self._wrap_tool(tool))

    def _wrap_tool(self, tool):
        """Create an MCP-callable wrapper for a registered tool.

        The wrapper exposes the tool's JSON schema as its own signature so the
        MCP runtime can build a correct pydantic argument model. It must not
        use ``functools.wraps``: that sets ``__wrapped__``, and
        ``inspect.signature`` would then follow through to ``tool.run`` whose
        unannotated ``**kwargs`` breaks pydantic model creation.
        """
        import inspect

        schema = tool.get_parameter_schema()
        properties = schema.get("properties", {}) or {}
        required = set(schema.get("required", []) or [])

        parameters = []
        for name, prop in properties.items():
            annotation = _json_type_to_python(prop.get("type"))
            if name in required:
                parameters.append(
                    inspect.Parameter(name, inspect.Parameter.KEYWORD_ONLY, annotation=annotation)
                )
            else:
                parameters.append(
                    inspect.Parameter(
                        name, inspect.Parameter.KEYWORD_ONLY, annotation=Optional[annotation], default=None
                    )
                )

        signature = inspect.Signature(parameters)

        def wrapper(**kwargs) -> Dict[str, Any]:
            args = {k: v for k, v in kwargs.items() if v is not None}
            # The server's repository path is the default target.
            args.setdefault("repository_path", self.repository_path)
            result = self.registry.execute(
                tool_name=tool.name,
                arguments=args,
                repository_path=self.repository_path,
                permission_manager=self.permission_manager,
                task_id="mcp_task",
            )
            if result.success:
                return {"success": True, "output": result.output, "duration_ms": result.duration_ms}
            return {"success": False, "error": result.error, "duration_ms": result.duration_ms}

        wrapper.__name__ = tool.name
        wrapper.__doc__ = tool.description
        wrapper.__signature__ = signature
        wrapper.__annotations__ = {
            p.name: p.annotation for p in parameters
        }
        wrapper.__annotations__["return"] = Dict[str, Any]
        return wrapper

    def get_registered_tool_names(self) -> List[str]:
        return [t.name for t in self.registry.list_tools()]

    def list_tool_specs(self) -> List[Dict[str, Any]]:
        return self.registry.get_tool_schemas()

    def discover(self) -> Dict[str, Any]:
        """Discovery payload: server info + available tools."""
        return {
            "server": "RepoLens MCP",
            "version": "2.0.0",
            "repository_path": self.repository_path,
            "tool_count": len(self.registry.list_tools()),
            "tools": self.get_registered_tool_names(),
        }

    def run_server(self, transport: str = "stdio"):
        self.mcp.run(transport=transport)


# Convenience factory for external callers
mcp_server: Optional[RepoLensMCPServer] = None


def get_mcp_server(repository_path: Optional[str] = None) -> RepoLensMCPServer:
    global mcp_server
    if mcp_server is None or (repository_path and mcp_server.repository_path != repository_path):
        mcp_server = RepoLensMCPServer(repository_path=repository_path)
    return mcp_server
