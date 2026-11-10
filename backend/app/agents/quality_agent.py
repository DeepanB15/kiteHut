"""
Code Quality Agent.

Analyzes maintainability and engineering quality.
"""

from app.agents.base_agent import BaseAgent
from app.models.agent_results import QualityResult
from app.models.repository_context import RepositoryContext
from app.prompts.quality_prompt import (
    QUALITY_SYSTEM_PROMPT,
    build_quality_prompt,
)


class QualityAgent(BaseAgent):
    """Code quality analysis agent."""

    def analyze(
        self,
        context: RepositoryContext,
        repository_path: str,
        recon_summary: str = "",
    ) -> QualityResult | None:
        """
        Run code quality analysis.

        Returns QualityResult or None if LLM fails.
        """

        print("\n  [Quality] Starting analysis...")

        context_data = self._select_context(
            context, repository_path
        )

        prompt = build_quality_prompt(
            context_data, recon_summary
        )

        result = self._safe_run(
            system_prompt=QUALITY_SYSTEM_PROMPT,
            prompt=prompt,
            model_class=QualityResult,
            agent_name="Quality",
        )

        if result:
            print(f"  [Quality] Summary: {result.quality_summary[:80]}...")
            print(f"  [Quality] Issues: {len(result.potential_issues)}")
            print(f"  [Quality] Refactoring candidates: {len(result.refactoring_candidates)}")

        return result
