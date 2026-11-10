"""
LLM Provider Factory.

Creates the appropriate LLM provider based on configuration.
Phase 2: Ollama only.
"""

import os

from app.llm.base import BaseLLMProvider


def create_llm_provider() -> BaseLLMProvider:
    """
    Create an LLM provider based on environment configuration.

    Phase 2: Always returns OllamaProvider.
    Future phases may support other providers.
    """

    provider_name = os.getenv("LLM_PROVIDER", "ollama")

    if provider_name == "ollama":
        from app.llm.ollama_provider import OllamaProvider
        return OllamaProvider()

    raise ValueError(f"Unknown LLM provider: {provider_name}")
