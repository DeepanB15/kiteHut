"""
Phase 8.2 — Embedding Configuration (configuration-driven, no hard-coded model).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional


DEFAULT_PROVIDER = "ollama"
DEFAULT_MODEL = os.getenv("EMBEDDING_MODEL", "nomic-embed-text")
DEFAULT_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
DEFAULT_BATCH_SIZE = 16


@dataclass
class EmbeddingConfig:
    """Configuration for the local embedding layer."""

    provider: str = DEFAULT_PROVIDER
    model: str = DEFAULT_MODEL
    base_url: str = DEFAULT_BASE_URL
    timeout: int = 60
    batch_size: int = DEFAULT_BATCH_SIZE
    store_path: Optional[str] = None

    @classmethod
    def from_env(cls) -> "EmbeddingConfig":
        """Load configuration from environment variables."""
        return cls(
            provider=os.getenv("EMBEDDING_PROVIDER", DEFAULT_PROVIDER),
            model=os.getenv("EMBEDDING_MODEL", DEFAULT_MODEL),
            base_url=os.getenv("OLLAMA_BASE_URL", DEFAULT_BASE_URL),
            timeout=int(os.getenv("EMBEDDING_TIMEOUT", "60")),
            batch_size=int(os.getenv("EMBEDDING_BATCH_SIZE", str(DEFAULT_BATCH_SIZE))),
            store_path=os.getenv("EMBEDDING_STORE_PATH"),
        )

    def validate(self) -> None:
        """Raise if the configuration is unusable."""
        if not self.model:
            raise ValueError("Embedding model name must not be empty")
        if not self.provider:
            raise ValueError("Embedding provider must not be empty")
