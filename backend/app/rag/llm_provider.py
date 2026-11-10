"""
Phase 8.6 — Local LLM Provider Wrapper.

Wraps the existing Ollama provider for Phase 8.6 RAG integration.
Reuses existing abstractions; does not duplicate the Ollama client.

Conceptually:
  LLMProvider
    ↓
  OllamaProvider (existing)
    ↓
  RAG LLM Wrapper (this module)

Follows existing project conventions from app.llm.base and app.llm.ollama_provider.
"""

from __future__ import annotations

import logging
from typing import Optional, Dict, Any

from app.llm.base import BaseLLMProvider, LLMProviderError

logger = logging.getLogger("repolens.rag.llm_provider")


class RagLlmProvider(BaseLLMProvider):
    """
    LLM provider specialized for RAG (Retrieval-Augmented Generation).

    Wraps the existing OllamaProvider to provide a simplified interface
    for the RAG pipeline. Handles Ollama availability, error wrapping,
    and configuration passthrough.

    The underlying OllamaProvider is reused directly — no duplicate HTTP
    client or model management.
    """

    # Tests can inject a deterministic response for offline verification
    _test_response: Optional[str] = None

    def __init__(
        self,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: int = 120,
        _test_response: Optional[str] = None,
    ):
        from app.llm.ollama_provider import OllamaProvider
        self._ollama = OllamaProvider(
            base_url=base_url,
            model=model,
            timeout=timeout,
        )
        if _test_response is not None:
            self._test_response = _test_response

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
    ) -> str:
        """
        Generate a response from the local LLM.

        Args:
            prompt: The user prompt / question.
            system_prompt: Optional system-level instructions.

        Returns:
            The model's text response.

        Raises:
            LLMProviderError: If the call fails (Ollama unavailable, etc.).
        """
        # Tests can inject a deterministic response for offline verification
        if getattr(self, '_test_response', None) is not None:
            return self._test_response
        # Class-level fallback for global mock injection
        if RagLlmProvider._test_response is not None:
            return RagLlmProvider._test_response
        try:
            return self._ollama.generate(prompt, system_prompt)
        except Exception as error:
            logger.error("LLM generation failed: %s", error)
            raise LLMProviderError(
                f"Local LLM generation failed: {error}"
            )

    def is_available(self) -> bool:
        """Check if Ollama is reachable."""
        return self._ollama.is_available()

    def list_models(self) -> list[str]:
        """List available models on the Ollama server."""
        return self._ollama.list_models()


class RagLlmProviderError(LLMProviderError):
    """Raised when an RAG LLM provider call fails."""

    pass