"""
Testing Agent.

Evaluates repository testing maturity.
"""

from app.agents.base_agent import BaseAgent
from app.models.agent_results import TestingResult
from app.models.repository_context import RepositoryContext
from app.prompts.testing_prompt import (
    TESTING_SYSTEM_PROMPT,
    build_testing_prompt,
)


class TestingAgent(BaseAgent):
    """Testing analysis agent."""

    def analyze(
        self,
        context: RepositoryContext,
        repository_path: str,
        recon_summary: str = "",
    ) -> TestingResult | None:
        """
        Run testing analysis.

        Returns TestingResult or None if LLM fails.
        """

        print("\n  [Testing] Starting analysis...")

        context_data = self._select_context(
            context, repository_path
        )

        prompt = build_testing_prompt(
            context_data, recon_summary
        )

        result = self._safe_run(
            system_prompt=TESTING_SYSTEM_PROMPT,
            prompt=prompt,
            model_class=TestingResult,
            agent_name="Testing",
        )

        if result:
            print(f"  [Testing] Maturity: {result.testing_maturity}")
            print(f"  [Testing] Frameworks: {result.test_frameworks}")
            print(f"  [Testing] Tested: {len(result.tested_components)}")
            print(f"  [Testing] Untested: {len(result.potentially_untested_components)}")

        return result
