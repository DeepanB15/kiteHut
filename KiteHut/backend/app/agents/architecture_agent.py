"""
Architecture Agent.

Analyzes the structural design of the repository.
"""

from app.agents.base_agent import BaseAgent
from app.models.agent_results import ArchitectureResult
from app.models.repository_context import RepositoryContext
from app.prompts.architecture_prompt import (
    ARCHITECTURE_SYSTEM_PROMPT,
    build_architecture_prompt,
)


class ArchitectureAgent(BaseAgent):
    """Architecture analysis agent."""

    def analyze(
        self,
        context: RepositoryContext,
        repository_path: str,
        recon_summary: str = "",
    ) -> ArchitectureResult | None:
        """
        Run architecture analysis.

        Returns ArchitectureResult or None if LLM fails.
        """

        print("\n  [Architecture] Starting analysis...")

        context_data = self._select_context(
            context, repository_path
        )

        prompt = build_architecture_prompt(
            context_data, recon_summary
        )

        result = self._safe_run(
            system_prompt=ARCHITECTURE_SYSTEM_PROMPT,
            prompt=prompt,
            model_class=ArchitectureResult,
            agent_name="Architecture",
        )

        if result:
            print(f"  [Architecture] Pattern: {result.architecture_pattern}")
            print(f"  [Architecture] Components: {len(result.components)}")
            print(f"  [Architecture] Issues: {len(result.potential_issues)}")

        return result
