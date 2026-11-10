"""
Phase 8.3 — Vector Retrieval.

Top-K nearest-neighbor retrieval over a LocalVectorIndex.
Exposes a clean API for consuming embedding records and returning
deterministic ranked results.

Conceptual flow:
    EmbeddingRecord
        ↓
    LocalVectorIndex
        ↓
    cosine_similarity
        ↓
    Top-K retrieval
        ↓
    RetrievalResult
"""

from __future__ import annotations

from typing import List, Optional

from app.embedding.record import EmbeddingRecord
from app.retrieval.local_index import LocalVectorIndex, RetrievalResult


class VectorRetrieval:
    """High-level retrieval service over a LocalVectorIndex."""

    def __init__(self, index: LocalVectorIndex):
        self.index = index

    def retrieve(
        self,
        query_vector: List[float],
        top_k: int = 10,
    ) -> List[RetrievalResult]:
        """Retrieve the top-k most similar chunks to the query vector.

        Args:
            query_vector: The query embedding vector.
            top_k: Maximum number of results to return.

        Returns:
            List of RetrievalResult sorted by similarity (highest first),
            with deterministic tie-breaking.
        """
        return self.index.search(query_vector, top_k=top_k)

    def retrieve_by_record(
        self,
        query_record: EmbeddingRecord,
        top_k: int = 10,
    ) -> List[RetrievalResult]:
        """Retrieve top-k similar to a given EmbeddingRecord's vector.

        Convenience method that extracts the vector from a record and
        delegates to retrieve().
        """
        return self.retrieve(query_record.vector, top_k=top_k)

    def get_by_chunk_id(self, chunk_id: str) -> Optional[RetrievalResult]:
        """Get a single retrieval result by chunk_id (similarity 1.0 if found)."""
        record = self.index.get(chunk_id)
        if record is None:
            return None
        return RetrievalResult(
            chunk_id=chunk_id,
            similarity_score=1.0,
            file_path=record.file_path if hasattr(record, 'file_path') else None,
            symbol_name=record.symbol_name if hasattr(record, 'symbol_name') else None,
            symbol_type=record.symbol_type if hasattr(record, 'symbol_type') else None,
            start_line=record.start_line if hasattr(record, 'start_line') else None,
            end_line=record.end_line if hasattr(record, 'end_line') else None,
            content_hash=record.content_hash if hasattr(record, 'content_hash') else None,
        )

    def contains(self, chunk_id: str) -> bool:
        """Check if a chunk_id is in the index."""
        return self.index.contains(chunk_id)

    def size(self) -> int:
        """Return the number of indexed records."""
        return len(self.index)