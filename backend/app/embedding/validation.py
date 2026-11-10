"""
Phase 8.2 — Embedding Validation.

Rejects invalid provider responses: empty, non-numeric, NaN, dimension mismatch.
"""
from __future__ import annotations

import math
from typing import List, Optional

from .record import EmbeddingRecord


class EmbeddingValidationError(ValueError):
    """Raised when a vector fails validation."""


def validate_vector(vector: Optional[List[float]], dimension: Optional[int] = None) -> List[float]:
    """
    Validate a raw provider vector.

    Checks:
      - vector exists and is non-empty
      - every element is numeric (int/float, not bool)
      - no NaN / inf values
      - length matches ``dimension`` when provided
    """
    if vector is None:
        raise EmbeddingValidationError("Embedding vector is missing")
    if not isinstance(vector, (list, tuple)):
        raise EmbeddingValidationError(f"Embedding vector must be a list, got {type(vector).__name__}")
    if len(vector) == 0:
        raise EmbeddingValidationError("Embedding vector is empty")

    validated: List[float] = []
    for index, value in enumerate(vector):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise EmbeddingValidationError(
                f"Embedding vector element {index} is not numeric: {value!r}"
            )
        number = float(value)
        if math.isnan(number) or math.isinf(number):
            raise EmbeddingValidationError(
                f"Embedding vector element {index} is NaN or infinite"
            )
        validated.append(number)

    if dimension is not None and len(validated) != dimension:
        raise EmbeddingValidationError(
            f"Embedding dimension mismatch: expected {dimension}, got {len(validated)}"
        )

    return validated


def validate_record(record: EmbeddingRecord) -> EmbeddingRecord:
    """Validate a full embedding record, including stored dimension consistency."""
    validate_vector(record.vector, dimension=record.dimension)
    return record
