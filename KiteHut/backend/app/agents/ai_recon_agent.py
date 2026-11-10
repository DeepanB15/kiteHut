"""
AI Recon Agent.

Extends the deterministic recon with LLM-powered reasoning.
Reads key files and produces deeper insights.
"""

from app.agents.base_agent import BaseAgent
from app.models.agent_results import AIReconResult
from app.models.repository_context import RepositoryContext
from app.prompts.recon_prompt import (
    RECON_SYSTEM_PROMPT,
    build_recon_prompt,
)


class AIReconAgent(BaseAgent):
    """AI-powered reconnaissance agent."""

    def analyze(
        self,
        context: RepositoryContext,
        repository_path: str,
    ) -> AIReconResult | None:
        """
        Run AI-powered recon analysis.

        Returns AIReconResult or None if LLM fails.
        """

        print("\n  [AI Recon] Starting analysis...")

        # Select relevant context
        context_data = self._select_context(
            context, repository_path
        )

        # Build prompt
        prompt = build_recon_prompt(context_data)

        # Run with LLM
        result = self._safe_run(
            system_prompt=RECON_SYSTEM_PROMPT,
            prompt=prompt,
            model_class=AIReconResult,
            agent_name="AI Recon",
        )

        if result:
            print(f"  [AI Recon] Purpose: {result.project_purpose[:80]}...")
            print(f"  [AI Recon] Type: {result.application_type}")
            print(f"  [AI Recon] Components: {len(result.major_components)}")
            print(f"  [AI Recon] Observations: {len(result.observations)}")

        return result
