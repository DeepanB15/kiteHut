"""
Context Manager for RepoLens Agent.

Manages LLM context window budgeting, system prompt formulation,
sliding conversation history windows, and dynamic file snippet injection.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional

from app.agent.state.agent_state import AgentState, Plan, ToolResult


class AgentContextManager:
    """
    Manages token budgeting and prompt assembly for agent reasoning steps.
    """

    DEFAULT_MAX_CONTEXT_TOKENS = 8192
    DEFAULT_RESERVED_RESPONSE_TOKENS = 1500
    ESTIMATED_CHARS_PER_TOKEN = 3.5

    def __init__(
        self,
        repository_path: str,
        max_context_tokens: int = DEFAULT_MAX_CONTEXT_TOKENS,
    ):
        self.repository_path = Path(repository_path).resolve()
        self.max_context_tokens = max_context_tokens
        self.available_prompt_tokens = max_context_tokens - self.DEFAULT_RESERVED_RESPONSE_TOKENS

    def estimate_tokens(self, text: str) -> int:
        """Estimate token count based on average character length."""
        return int(len(text) / self.ESTIMATED_CHARS_PER_TOKEN) + 1

    def build_system_prompt(
        self,
        user_goal: str,
        available_tools: Optional[List[Dict[str, Any]]] = None,
        project_summary: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Build the foundational system prompt for the agent runtime.
        """
        prompt_parts = [
            "You are RepoLens, an autonomous local AI engineering agent and repository guardian.",
            f"Repository root: {self.repository_path}",
            f"Goal: {user_goal}",
            "",
            "CORE PRODUCT PRINCIPLES:",
            "1. Local-first: Never send credentials or code off-machine.",
            "2. Evidence-based: Verify findings and assertions directly against code and tests.",
            "3. Observe -> Understand -> Plan -> Act -> Test -> Verify -> Report -> Repeat.",
            "4. Precision: When editing files, provide exact search segments and replacements.",
            "5. Safety: Destructive or modifying actions require confirmation/approval.",
            "",
        ]

        if project_summary:
            prompt_parts.extend([
                "PROJECT CONTEXT:",
                f"- Primary Language: {project_summary.get('primary_language', 'Auto-detected')}",
                f"- Frameworks: {', '.join(project_summary.get('frameworks', [])) or 'None detected'}",
                f"- File Count: {project_summary.get('file_count', 'N/A')}",
                "",
            ])

        if available_tools:
            prompt_parts.extend([
                "AVAILABLE TOOLS:",
                "You have access to the following tools to inspect, edit, and test code:",
            ])
            for tool in available_tools:
                name = tool.get("name", "tool")
                desc = tool.get("description", "")
                prompt_parts.append(f"- {name}: {desc}")
            prompt_parts.append("")

        prompt_parts.extend([
            "OUTPUT FORMAT FOR TOOL CALLS:",
            "When executing a tool, return a JSON block:",
            '```json\n{"tool": "<tool_name>", "arguments": {<arguments>}}\n```',
            "When ready to give a final response or explanation, output clear markdown text.",
        ])

        return "\n".join(prompt_parts)

    def assemble_step_prompt(
        self,
        state: AgentState,
        step_description: str,
        expected_output: Optional[str] = None,
        extra_file_snippets: Optional[Dict[str, str]] = None,
        available_tools: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """
        Assemble the complete prompt for executing a specific plan step.
        """
        system_base = self.build_system_prompt(
            user_goal=state.user_goal,
            available_tools=available_tools,
        )

        budget = self.available_prompt_tokens - self.estimate_tokens(system_base)

        # File snippets section
        snippets_text = ""
        if extra_file_snippets:
            snippet_lines = ["\n--- RELEVANT CODE SNIPPETS ---"]
            for fpath, content in extra_file_snippets.items():
                truncated = self._truncate_content(content, max_lines=150)
                snippet_lines.append(f"File: {fpath}\n```\n{truncated}\n```\n")
            snippets_text = "\n".join(snippet_lines)
            budget -= self.estimate_tokens(snippets_text)

        # Recent tool execution history
        history_lines = ["\n--- RECENT TOOL EXECUTION HISTORY ---"]
        for res in state.tool_history[-5:]:
            status_str = "SUCCESS" if res.success else f"FAILED: {res.error}"
            out_preview = self._truncate_content(res.output or "", max_lines=20)
            history_lines.append(f"[{res.tool_name}] -> {status_str}\nOutput: {out_preview}")
        history_text = "\n".join(history_lines) if len(state.tool_history) > 0 else ""

        # Step instructions
        step_instructions = [
            f"\nCURRENT PLAN STEP ({state.current_step_index + 1}): {step_description}",
            f"Expected Outcome: {expected_output or 'Perform action accurately'}",
            "Decide the next tool to call or provide the required code modification/analysis.",
        ]
        step_text = "\n".join(step_instructions)

        return system_base + snippets_text + history_text + "\n" + step_text

    def _truncate_content(self, content: str, max_lines: int = 150) -> str:
        """Truncates multi-line content to stay within budgeting limits."""
        lines = content.splitlines()
        if len(lines) <= max_lines:
            return content
        return "\n".join(lines[:max_lines]) + f"\n... [{len(lines) - max_lines} lines truncated] ..."
