"""
Phase 8.2 — Embedding Record.

Keeps chunk identity, content hash, model info, vector, and dimension.
Timestamps are NOT used as part of identity (only optional audit fields).
"""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


class EmbeddingRecord(BaseModel):
    """A single embedding result linked to a chunk and model."""

    chunk_id: str
    content_hash: str
    model_name: str
    dimension: int = Field(ge=1)
    vector: List[float] = Field(default_factory=list)

    def is_reusable_for(self, chunk_id: str, content_hash: str, model_name: str, dimension: int) -> bool:
        return (
            self.chunk_id == chunk_id
            and self.content_hash == content_hash
            and self.model_name == model_name
            and self.dimension == dimension
        )

    @field_validator("vector")
    @classmethod
    def _non_empty(cls, v: List[float]) -> List[float]:
        if not v:
            raise ValueError("Embedding vector must not be empty")
        return v
