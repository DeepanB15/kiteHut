"""
Base LLM Provider interface.

All LLM providers must implement this interface.
Phase 2 uses Ollama only.
Future phases may add OpenAI, Anthropic, Gemini.
"""

from abc import ABC, abstractmethod


class BaseLLMProvider(ABC):
    """Abstract base class for LLM providers."""

    @abstractmethod
    def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
    ) -> str:
        """
        Generate a response from the LLM.

        Args:
            prompt: The user prompt / question.
            system_prompt: Optional system-level instructions.

        Returns:
            The model's text response.

        Raises:
            LLMProviderError: If the call fails.
        """
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if the LLM provider is reachable."""
        pass


class LLMProviderError(Exception):
    """Raised when an LLM provider call fails."""
