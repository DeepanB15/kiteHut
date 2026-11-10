"""
Agent Router — Phase 9.2.

Deterministic decision layer: AgentTask -> Tool Selection Decision.
No MCP execution. No side effects. No autonomous execution.
"""

from typing import List, Optional, Dict
from pydantic import BaseModel, Field
from enum import Enum


class ToolCategory(str, Enum):
    RETRIEVAL = "RETRIEVAL"
    CODE = "CODE"
    GIT = "GIT"
    ANALYSIS = "ANALYSIS"
    TESTING = "TESTING"
    REVIEW = "REVIEW"
    SYSTEM = "SYSTEM"


class ToolCapability(BaseModel):
    tool_name: str = Field(description="Registered MCP tool name")
    category: ToolCategory = Field(description="Capability category")
    description: str = Field(default="", description="Short description")
    read_only: bool = Field(default=True, description="True if read-only")
    requires_approval: bool = Field(default=False, description="True if privileged/mutating")

    model_config = {"validate_by_name": True}


class ToolDecision(BaseModel):
    decision_id: str = Field(description="Unique decision identifier")
    task_id: str = Field(description="Reference to AgentTask.task_id")
    tool_name: str = Field(description="Selected registered capability")
    category: ToolCategory = Field(description="Category of selected tool")
    reason: str = Field(description="Routing reason / explanation")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="Confidence score")
    requires_confirmation: bool = Field(default=False, description="Requires user approval")

    model_config = {"validate_by_name": True}


class ToolSelection(BaseModel):
    primary_tool: ToolDecision = Field(description="Primary selected tool")
    supporting_tools: List[ToolDecision] = Field(default_factory=list, description="Supporting tools")
    ambiguity: bool = Field(default=False, description="True if routing was ambiguous")
    clarification_needed: bool = Field(default=False, description="True if clarification required")

    model_config = {"validate_by_name": True}


# Controlled registry of the 23 existing MCP capabilities (exact names from registry)
TOOL_REGISTRY: Dict[str, ToolCapability] = {
    "search_code": ToolCapability(tool_name="search_code", category=ToolCategory.RETRIEVAL, description="Search code by pattern", read_only=True, requires_approval=False),
    "search_files": ToolCapability(tool_name="search_files", category=ToolCategory.RETRIEVAL, description="Search files by name", read_only=True, requires_approval=False),
    "find_symbol": ToolCapability(tool_name="find_symbol", category=ToolCategory.RETRIEVAL, description="Find symbol definition", read_only=True, requires_approval=False),
    "list_files": ToolCapability(tool_name="list_files", category=ToolCategory.RETRIEVAL, description="List directory contents", read_only=True, requires_approval=False),
    "get_repo_structure": ToolCapability(tool_name="get_repo_structure", category=ToolCategory.RETRIEVAL, description="Get repository structure", read_only=True, requires_approval=False),
    "read_file": ToolCapability(tool_name="read_file", category=ToolCategory.CODE, description="Read file contents", read_only=True, requires_approval=False),
    "get_dependencies": ToolCapability(tool_name="get_dependencies", category=ToolCategory.ANALYSIS, description="Get project dependencies", read_only=True, requires_approval=False),
    "run_analysis": ToolCapability(tool_name="run_analysis", category=ToolCategory.ANALYSIS, description="Run analysis", read_only=True, requires_approval=False),
    "git_status": ToolCapability(tool_name="git_status", category=ToolCategory.GIT, description="Git working tree status", read_only=True, requires_approval=False),
    "git_diff": ToolCapability(tool_name="git_diff", category=ToolCategory.GIT, description="Show git diff", read_only=True, requires_approval=False),
    "get_git_diff": ToolCapability(tool_name="get_git_diff", category=ToolCategory.GIT, description="Show git diff", read_only=True, requires_approval=False),
    "git_log": ToolCapability(tool_name="git_log", category=ToolCategory.GIT, description="Show git log", read_only=True, requires_approval=False),
    "get_git_log": ToolCapability(tool_name="get_git_log", category=ToolCategory.GIT, description="Show git log", read_only=True, requires_approval=False),
    "git_branch": ToolCapability(tool_name="git_branch", category=ToolCategory.GIT, description="List branches", read_only=True, requires_approval=False),
    "run_tests": ToolCapability(tool_name="run_tests", category=ToolCategory.TESTING, description="Run project tests", read_only=False, requires_approval=True),
    "run_linter": ToolCapability(tool_name="run_linter", category=ToolCategory.TESTING, description="Run linter", read_only=False, requires_approval=True),
    "run_typecheck": ToolCapability(tool_name="run_typecheck", category=ToolCategory.TESTING, description="Run type checker", read_only=False, requires_approval=True),
    "write_file": ToolCapability(tool_name="write_file", category=ToolCategory.CODE, description="Write file", read_only=False, requires_approval=True),
    "edit_file": ToolCapability(tool_name="edit_file", category=ToolCategory.CODE, description="Edit file", read_only=False, requires_approval=True),
    "delete_file": ToolCapability(tool_name="delete_file", category=ToolCategory.SYSTEM, description="Delete file", read_only=False, requires_approval=True),
    "run_command": ToolCapability(tool_name="run_command", category=ToolCategory.SYSTEM, description="Run shell command", read_only=False, requires_approval=True),
    "git_commit": ToolCapability(tool_name="git_commit", category=ToolCategory.GIT, description="Create git commit", read_only=False, requires_approval=True),
    "git_checkout": ToolCapability(tool_name="git_checkout", category=ToolCategory.GIT, description="Checkout branch", read_only=False, requires_approval=True),
}


def get_registry() -> Dict[str, ToolCapability]:
    return dict(TOOL_REGISTRY)


def get_registered_tool_names() -> List[str]:
    return list(TOOL_REGISTRY.keys())
