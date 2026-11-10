"""
Phase 8.2 — Embedding Indexing Service.

Accepts Phase 8.1 chunks, produces embeddings, tracks reuse/generated/failed.
No semantic search — only indexing and persistence.
"""
from __future__ import annotations

from typing import Dict, List, Optional
from pathlib import Path

from app.chunking.model import CodeChunk
from app.embedding.config import EmbeddingConfig
from app.embedding.provider import EmbeddingError, EmbeddingProvider
from app.embedding.record import EmbeddingRecord
from app.embedding.store import EmbeddingStore
from app.embedding.validation import validate_vector

from .local_provider import OllamaEmbeddingProvider


class IndexSummary:
    """Deterministic summary of an indexing pass."""

    def __init__(self):
        self.total = 0
        self.reused = 0
        self.generated = 0
        self.failed = 0

    def to_dict(self) -> Dict[str, int]:
        return {
            "total": self.total,
            "reused": self.reused,
            "generated": self.generated,
            "failed": self.failed,
        }


class EmbeddingIndexer:
    """Indexes Phase 8.1 chunks with local embeddings."""

    def __init__(
        self,
        store: Optional[EmbeddingStore] = None,
        provider: Optional[EmbeddingProvider] = None,
        config: Optional[EmbeddingConfig] = None,
    ):
        self.config = config or EmbeddingConfig.from_env()
        self.provider = provider or OllamaEmbeddingProvider(self.config)
        if store is not None:
            self.store = store
        else:
            import tempfile
            tmp_dir = tempfile.mkdtemp(prefix="repolens_8_2_")
            self.store = EmbeddingStore(str(Path(tmp_dir) / "embeddings.jsonl"))

    def index_chunks(self, chunks: List[CodeChunk]) -> IndexSummary:
        summary = IndexSummary()
        summary.total = len(chunks)

        for chunk in chunks:
            record = self.store.get(chunk.chunk_id)
            reused = False
            if record is not None:
                # Must match content hash, model name, AND dimension.
                if (record.content_hash == chunk.content_hash
                        and record.model_name == self.provider.model_name
                        and record.dimension == self.provider.dimension):
                    reused = True
            if reused:
                summary.reused += 1
                continue

            try:
                vector = self.provider.embed_text(chunk.content)
                # After embed, discover dimension from the actual vector produced.
                dimension = len(vector)
                record = EmbeddingRecord(
                    chunk_id=chunk.chunk_id,
                    content_hash=chunk.content_hash,
                    model_name=self.provider.model_name,
                    dimension=dimension,
                    vector=vector,
                )
                validate_vector(record.vector, dimension=record.dimension)
                self.store.save(record)
                summary.generated += 1
            except (EmbeddingError, ValueError):
                summary.failed += 1
                # Do not corrupt store; preserve existing records.

        return summary

    def _resolve_dimension(self, vector: List[float]) -> int:
        """
        Determine the dimension for a freshly produced vector.

        The provider's declared dimension wins when it is known. Otherwise
        the actual vector length is used — the dimension is never assumed.
        """
        try:
            declared = int(self.provider.dimension)
        except Exception:
            declared = 0
        if declared > 0:
            return declared
        if not vector:
            raise EmbeddingError("Provider returned an empty embedding vector")
        return len(vector)

        return summary

    def index_chunk(self, chunk: CodeChunk) -> bool:
        """Index a single chunk. Returns True on success (reused or generated)."""
        summary = self.index_chunks([chunk])
        return summary.reused + summary.generated > 0

    def get_embedding(self, chunk_id: str) -> Optional[EmbeddingRecord]:
        return self.store.get(chunk_id)
