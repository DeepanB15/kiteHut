"""
Phase 8.2 — Local Embedding Provider (Ollama).

Local-only. No cloud embedding API. The vector dimension is discovered
from the provider response, never assumed.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import List, Optional

from .config import EmbeddingConfig
from .provider import EmbeddingError, EmbeddingProvider
from .validation import validate_vector


class OllamaEmbeddingProvider(EmbeddingProvider):
    """Embedding provider backed by a local Ollama server."""

    def __init__(self, config: Optional[EmbeddingConfig] = None):
        self.config = config or EmbeddingConfig.from_env()
        self.config.validate()
        self._dimension: Optional[int] = None

    # -- interface ----------------------------------------------------

    @property
    def model_name(self) -> str:
        return self.config.model

    @property
    def dimension(self) -> int:
        """Dimension of the vectors produced by this provider.

        Discovered from the first successful embedding. Raises if the
        provider has not produced a vector yet.
        """
        if self._dimension is None:
            raise EmbeddingError(
                "Embedding dimension is not known yet — embed at least one text first"
            )
        return self._dimension

    def embed_text(self, text: str) -> List[float]:
        vectors = self.embed_texts([text])
        return vectors[0]

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []

        vectors: List[List[float]] = []
        for text in texts:
            vectors.append(self._embed_one(text))

        for vector in vectors:
            if self._dimension is None:
                self._dimension = len(vector)
            elif len(vector) != self._dimension:
                raise EmbeddingError(
                    f"Inconsistent embedding dimension from provider: "
                    f"expected {self._dimension}, got {len(vector)}"
                )
        return vectors

    # -- internals ----------------------------------------------------

    def _embed_one(self, text: str) -> List[float]:
        payload = json.dumps({
            "model": self.config.model,
            "prompt": text,
            "stream": False,
        }).encode("utf-8")

        url = f"{self.config.base_url}/api/embeddings"

        try:
            req = urllib.request.Request(
                url,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=self.config.timeout) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.URLError as error:
            raise EmbeddingError(
                f"Cannot connect to Ollama at {self.config.base_url}. "
                f"Is Ollama running? Error: {error}"
            )
        except (KeyError, json.JSONDecodeError) as error:
            raise EmbeddingError(f"Invalid response from Ollama: {error}")
        except Exception as error:
            raise EmbeddingError(f"Ollama embedding request failed: {error}")

        raw = data.get("embedding")
        if raw is None:
            raise EmbeddingError("Ollama response contained no 'embedding' field")

        # Validate BEFORE trusting the vector.
        return validate_vector(raw)
