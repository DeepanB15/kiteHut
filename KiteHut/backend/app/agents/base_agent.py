"""
Base Agent.

Shared logic for all AI agents: context selection, LLM calls,
JSON parsing, and Pydantic validation.
"""

import json
import re
from pathlib import Path

from pydantic import BaseModel

from app.llm.factory import create_llm_provider
from app.llm.base import LLMProviderError
from app.services.context_selector import select_context
from app.models.repository_context import RepositoryContext


class BaseAgent:
    """Base class for all AI-powered agents."""

    def __init__(self):
        self.llm = create_llm_provider()

    def _select_context(
        self,
        context: RepositoryContext,
        repository_path: str,
    ) -> dict:
        """Select relevant context for the agent."""

        return select_context(context, repository_path)

    def _call_llm(
        self,
        prompt: str,
        system_prompt: str,
    ) -> str:
        """Call the LLM and return the raw response."""

        return self.llm.generate(
            prompt=prompt,
            system_prompt=system_prompt,
        )

    def _parse_json_response(
        self,
        response: str,
    ) -> dict:
        """
        Parse JSON from an LLM response.

        Handles cases where the model wraps JSON in markdown
        code blocks or adds extra text.
        """

        # Try to extract JSON from markdown code blocks
        json_match = re.search(
            r"```(?:json)?\s*\n?(.*?)\n?\s*```",
            response,
            re.DOTALL,
        )

        if json_match:
            json_str = json_match.group(1).strip()
        else:
            # Try the entire response as JSON
            json_str = response.strip()

        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            # Try to find JSON object in the response
            brace_start = json_str.find("{")
            brace_end = json_str.rfind("}")

            if brace_start != -1 and brace_end != -1:
                try:
                    return json.loads(
                        json_str[brace_start:brace_end + 1]
                    )
                except json.JSONDecodeError:
                    pass

            raise ValueError(
                f"Could not parse JSON from LLM response. "
                f"Response starts with: {response[:200]}"
            )

    def _validate_result(
        self,
        data: dict,
        model_class: type[BaseModel],
    ) -> BaseModel:
        """Validate parsed data against a Pydantic model."""

        return model_class.model_validate(data)

    def _safe_run(
        self,
        system_prompt: str,
        prompt: str,
        model_class: type[BaseModel],
        agent_name: str,
    ) -> BaseModel | None:
        """
        Safely run an agent: call LLM, parse, validate.

        Returns the validated result, or None if anything fails.
        """

        try:
            # Check LLM availability
            if not self.llm.is_available():
                print(f"  [{agent_name}] LLM not available, skipping.")
                return None

            # Call LLM
            print(f"  [{agent_name}] Calling LLM...")
            response = self._call_llm(prompt, system_prompt)
            print(f"  [{agent_name}] Response received ({len(response)} chars)")

            # Parse JSON
            parsed = self._parse_json_response(response)

            # Validate with Pydantic
            result = self._validate_result(parsed, model_class)
            print(f"  [{agent_name}] Validation passed.")

            return result

        except LLMProviderError as error:
            print(f"  [{agent_name}] LLM error: {error}")
            return None

        except ValueError as error:
            print(f"  [{agent_name}] Parse error: {error}")
            return None

        except Exception as error:
            print(f"  [{agent_name}] Unexpected error: {error}")
            return None
