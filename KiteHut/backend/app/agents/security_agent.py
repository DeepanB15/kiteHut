"""
Security Agent.

Identifies potential security concerns in the repository.
"""

from app.agents.base_agent import BaseAgent
from app.models.agent_results import SecurityResult
from app.models.repository_context import RepositoryContext
from app.prompts.security_prompt import (
    SECURITY_SYSTEM_PROMPT,
    build_security_prompt,
)


class SecurityAgent(BaseAgent):
    """Security analysis agent."""

    def analyze(
        self,
        context: RepositoryContext,
        repository_path: str,
        recon_summary: str = "",
    ) -> SecurityResult | None:
        """
        Run security analysis.

        Returns SecurityResult or None if LLM fails.
        """

        print("\n  [Security] Starting analysis...")

        context_data = self._select_context(
            context, repository_path
        )

        prompt = build_security_prompt(
            context_data, recon_summary
        )

        result = self._safe_run(
            system_prompt=SECURITY_SYSTEM_PROMPT,
            prompt=prompt,
            model_class=SecurityResult,
            agent_name="Security",
        )

        if result:
            print(f"  [Security] Risks: {len(result.potential_risks)}")
            print(f"  [Security] Strengths: {len(result.security_strengths)}")
            print(f"  [Security] Observations: {len(result.security_observations)}")

        return result
