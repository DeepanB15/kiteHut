"""
Phase 8.3 — Local Vector Index.

A local in-process, brute-force nearest-neighbor vector index.
No external infrastructure, no ANN libraries, zero dependencies beyond
Phase 8.2 abstractions.

Key design decisions:
- Brute-force scan (correctness first; ANN can replace later)
- Dictionary-backed: chunk_id → EmbeddingRecord
- Deterministic ordering: similarity DESC, chunk_id ASC for ties
- Dimension-scoped: all vectors in an index must have the same dimension
- Rebuild-from-store support (see local_index.py)
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Set

from pydantic import BaseModel

from app.embedding.validation import EmbeddingValidationError
from app.chunking.model import CodeChunk
from app.embedding.record import EmbeddingRecord
from app.retrieval.similarity import cosine_similarity


class LocalVectorIndex:
    """
    Local brute-force vector index for cosine similarity retrieval.

    Responsibilities:
    - add / update / remove records
    - search (top-k cosine similarity)
    - rebuild from records
    - dimension enforcement
    """

    def __init__(self, dimension: int):
        self.dimension: int = dimension
        # chunk_id → EmbeddingRecord
        self._records: Dict[str, EmbeddingRecord] = {}
        # Track which chunk_ids have been removed (for rebuild compatibility)
        self._removed: Set[str] = set()

    # -- add / update / remove -------------------------------------------

    def add(self, record: EmbeddingRecord) -> None:
        """Add or update a record in the index.

        If chunk_id already exists, the new vector replaces the old one.
        Validates dimension compatibility.
        """
        if record.dimension != self.dimension:
            raise EmbeddingValidationError(
                f"Dimension mismatch: record has dimension {record.dimension}, "
                f"index has dimension {self.dimension}"
            )
        # If previously removed, remove from removed set so it's indexed again
        self._records[record.chunk_id] = record
        self._removed.discard(record.chunk_id)

    def remove(self, chunk_id: str) -> bool:
        """Remove a record from the index.

        Returns True if a record was found and removed.
        """
        if chunk_id in self._records:
            del self._records[chunk_id]
            self._removed.add(chunk_id)
            return True
        return False

    def contains(self, chunk_id: str) -> bool:
        """Check if a chunk_id is currently in the index."""
        return chunk_id in self._records and chunk_id not in self._removed

    def get(self, chunk_id: str) -> Optional[EmbeddingRecord]:
        """Get the embedding record for a chunk_id, or None."""
        return self._records.get(chunk_id)

    def clear(self) -> None:
        """Remove all records from the index."""
        self._records.clear()
        self._removed.clear()

    # -- search --------------------------------------------------------

    def search(self, query_vector: List[float], top_k: int = 10) -> List[RetrievalResult]:
        """Search for the top-k nearest neighbors using cosine similarity.

        Args:
            query_vector: The query vector.
            top_k: Number of results to return. If <= 0, returns empty list.
                   If > number of indexed vectors, returns all available.

        Returns:
            List of RetrievalResult sorted by similarity (highest first),
            with deterministic tie-breaking (chunk_id ASC).
        """
        if top_k is not None and top_k <= 0:
            return []

        # Validate query vector dimension
        if self._records:
            query_len = len(query_vector)
            # Check dimension compatibility
            if query_len != self.dimension:
                raise EmbeddingValidationError(
                    f"Query dimension {query_len} does not match index dimension {self.dimension}"
                )

        # Brute-force scan: compute similarity for all records
        scored: List[tuple[float, str]] = []
        for chunk_id, record in self._records.items():
            # Skip removed records
            if chunk_id in self._removed:
                continue
            try:
                sim = cosine_similarity(query_vector, record.vector, validate=False)
                scored.append((sim, chunk_id))
            except EmbeddingValidationError:
                # Skip records with invalid vectors
                continue

        # Sort: similarity DESC, chunk_id ASC for deterministic tie-breaking
        scored.sort(key=lambda x: (-x[0], x[1]))

        # Apply top_k
        k = min(top_k, len(scored)) if top_k is not None else len(scored)
        results: List[RetrievalResult] = []
        for sim, chunk_id in scored[:k]:
            record = self._records[chunk_id]
            results.append(
                RetrievalResult(
                    chunk_id=chunk_id,
                    similarity_score=sim,
                    file_path=record.file_path if hasattr(record, 'file_path') else None,
                    symbol_name=record.symbol_name if hasattr(record, 'symbol_name') else None,
                    symbol_type=record.symbol_type if hasattr(record, 'symbol_type') else None,
                    start_line=record.start_line if hasattr(record, 'start_line') else None,
                    end_line=record.end_line if hasattr(record, 'end_line') else None,
                    content_hash=record.content_hash if hasattr(record, 'content_hash') else None,
                )
            )

        return results

    # -- rebuild -------------------------------------------------------

    def rebuild(self, records: List[EmbeddingRecord]) -> None:
        """Rebuild the index from a list of EmbeddingRecords.

        Behavior:
        1. Clear current index
        2. Validate records
        3. Index valid/current records
        4. Reject incompatible dimensions
        5. Produce deterministic state
        """
        self.clear()
        for record in records:
            if record.dimension != self.dimension:
                # Skip incompatible records (dimension mismatch)
                continue
            # Check if this is a stale/removed record
            if record.chunk_id in self._removed:
                continue
            self.add(record)

    # -- batch operations ----------------------------------------------

    def add_all(self, records: List[EmbeddingRecord]) -> None:
        """Add multiple records to the index."""
        for record in records:
            self.add(record)

    def remove_all(self, chunk_ids: List[str]) -> None:
        """Remove multiple records from the index."""
        for chunk_id in chunk_ids:
            self.remove(chunk_id)

    @property
    def records(self) -> Dict[str, EmbeddingRecord]:
        """Return a copy of the current records dict."""
        return self._records.copy()

    @property
    def removed(self) -> Set[str]:
        """Return the set of removed chunk_ids."""
        return self._removed.copy()

    def __len__(self) -> int:
        return len(self._records)

    def __contains__(self, chunk_id: str) -> bool:
        return self.contains(chunk_id)


class RetrievalResult(BaseModel):
    """Result of a vector search query."""

    chunk_id: str
    similarity_score: float
    file_path: Optional[str] = None
    symbol_name: Optional[str] = None
    symbol_type: Optional[str] = None
    start_line: Optional[int] = None
    end_line: Optional[int] = None
    content_hash: Optional[str] = None