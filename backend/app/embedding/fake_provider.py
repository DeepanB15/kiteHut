"""
Phase 8.2 — Deterministic Fake Embedding Provider (tests only, no Ollama).
Produces a stable vector from text content — repeatable, deterministic.
"""
from __future__ import annotations

import hashlib
import math
from typing import List

from .config import EmbeddingConfig
from .provider import EmbeddingProvider


class FakeEmbeddingProvider(EmbeddingProvider):
    """Mock provider for offline testing.

    Vector dimension defaults to 384; derived deterministically from input text.
    No external server required.
    """

    DEFAULT_DIM = 384

    def __init__(self, config: EmbeddingConfig = None, dimension: int = DEFAULT_DIM):
        self.config = config or EmbeddingConfig.from_env()
        self._dimension = dimension

    @property
    def model_name(self) -> str:
        return "fake-embedding-model"

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed_text(self, text: str) -> List[float]:
        # Deterministic vector from text hash.
        seed = int(hashlib.sha256(text.encode("utf-8")).hexdigest(), 16)
        # Produce a fixed-size float array of the configured dimension.
        vector: List[float] = []
        for i in range(self._dimension):
            val = (math.sin(seed + i) + math.cos(seed * 0.5 + i)) / 2
            # Scale to [-1, 1], avoid exactly 0 for validation diversity
            val = val if abs(val) > 1e-6 else 1e-6
            vector.append(round(val, 6))
        # Validate that all elements are finite numbers (test self-check)
        for v in vector:
            if math.isnan(v) or math.isinf(v):
                raise RuntimeError("Fake provider produced invalid float")
        return vector

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        return [self.embed_text(t) for t in texts]
