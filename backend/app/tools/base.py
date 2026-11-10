"""
Base Tool Interface and Specifications for RepoLens.

All tools must extend BaseTool, specify their permissions and risk levels,
and provide standard JSON Schema parameter specifications.
"""

from abc import ABC, abstractmethod
import time
import uuid
from typing import Any, Dict, Optional

from app.agent.permissions.policies import PermissionType, RiskLevel
from app.agent.state.agent_state import ToolResult


class BaseTool(ABC):
    """Abstract base class for all agent-callable tools."""

    name: str
    description: str
    permission_type: PermissionType
    risk_level: RiskLevel

    @abstractmethod
    def get_parameter_schema(self) -> Dict[str, Any]:
        """
        Return the JSON Schema describing parameters for this tool.
        Compatible with OpenAI/Ollama/Claude tool definition formats.
        """
        pass

    @abstractmethod
    def run(self, **kwargs) -> str:
        """
        Execute the tool logic and return string output.
        Must raise an exception or return text.
        """
        pass

    def execute(self, call_id: Optional[str] = None, **kwargs) -> ToolResult:
        """
        Wrapper that measures execution duration, handles exceptions,
        and constructs a standardized ToolResult.
        """
        cid = call_id or f"call_{uuid.uuid4().hex[:8]}"
        start_time = time.perf_counter()

        try:
            output = self.run(**kwargs)
            duration = (time.perf_counter() - start_time) * 1000.0
            return ToolResult(
                call_id=cid,
                tool_name=self.name,
                success=True,
                output=output,
                duration_ms=round(duration, 2),
            )
        except Exception as error:
            duration = (time.perf_counter() - start_time) * 1000.0
            return ToolResult(
                call_id=cid,
                tool_name=self.name,
                success=False,
                error=str(error),
                duration_ms=round(duration, 2),
            )

    def to_tool_spec(self) -> Dict[str, Any]:
        """Convert the tool into a standard LLM function/tool schema."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.get_parameter_schema(),
            },
        }
