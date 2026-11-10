"""
Phase 8.2 — Embedding package.

Provides: provider interface, local provider, fake provider, store,
record, validation, indexer, config.
No semantic search yet (Phase 8.3).
"""
from .provider import EmbeddingProvider, EmbeddingError
from .local_provider import OllamaEmbeddingProvider
from .fake_provider import FakeEmbeddingProvider
from .record import EmbeddingRecord
from .store import EmbeddingStore
from .validation import validate_vector, EmbeddingValidationError
from .indexer import EmbeddingIndexer, IndexSummary
from .config import EmbeddingConfig

__all__ = [
    "EmbeddingProvider",
    "EmbeddingError",
    "OllamaEmbeddingProvider",
    "FakeEmbeddingProvider",
    "EmbeddingRecord",
    "EmbeddingStore",
    "validate_vector",
    "EmbeddingValidationError",
    "EmbeddingIndexer",
    "IndexSummary",
    "EmbeddingConfig",
]
