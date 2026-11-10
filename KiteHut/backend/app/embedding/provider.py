"""
Phase 8.2 — Embedding Provider Abstraction.

No direct dependency on cloud embedding APIs.
Local-first, configuration-driven.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional


class EmbeddingError(Exception):
    """Raised when embedding generation or validation fails."""


class EmbeddingProvider(ABC):
    """Abstract interface for embedding providers."""

    @property
    @abstractmethod
    def model_name(self) -> str:
        ...

    @property
    @abstractmethod
    def dimension(self) -> int:
        ...

    @abstractmethod
    def embed_text(self, text: str) -> List[float]:
        ...

    @abstractmethod
    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        ...
