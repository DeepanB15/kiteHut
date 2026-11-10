"""
Phase 3 — Local Agent Loop (bounded, evidence-backed, tool-using).

Purpose: receive a user question, decide which repo tools to run,
observe results, reason, optionally call more tools (max 5), and
return a final answer based on observed evidence — not just LLM text.

Consciously NOT implemented (later phases):
- LangGraph
- multi-agent orchestration
- RAG / embeddings / vector DB
- Tree-sitter
- autonomous editing / commits
- self-correction / retry beyond max iterations
- GitHub agent
- PostgreSQL / Redis
"""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("repolens.agent.investigate")

MAX_ITERATIONS = 5


class InvestigationResult:
    """Evidence-backed result from a local-agent investigation."""

    def __init__(
        self,
        user_question: str,
        iterations: int = 0,
        tool_calls: Optional[List[Dict[str, Any]]] = None,
        observations: Optional[List[str]] = None,
        final_answer: str = "",
        error: str = "",
    ):
        self.user_question = user_question
        self.iterations = iterations
        self.tool_calls = tool_calls or []
        self.observations = observations or []
        self.final_answer = final_answer
        self.error = error

    def has_tool_evidence(self) -> bool:
        return len(self.tool_calls) > 0

    def summarize_evidence(self) -> str:
        lines = [f"Investigation of: {self.user_question}", f"Iterations: {self.iterations}", f"Tools executed: {len(self.tool_calls)}"]
        for call in self.tool_calls:
            lines.append(f"  - {call.get('tool', '?')}: {call.get('status', '?')}")
        lines.append("Observations:")
        for obs in (self.observations or [])[-3:]:
            lines.append(f"  - {str(obs)[:180]}")
        return "\n".join(lines)
