"""
Phase 8.3 — Cosine Similarity.

Provides deterministic cosine similarity between numeric vectors.
Reuses Phase 8.2 validation/validation logic where appropriate.

Formula:
    cos(A, B) = (A · B) / (||A|| ||B||)

Rules:
- numeric vectors only
- equal dimensions
- finite values (reject NaN / inf)
- non-empty vectors
- safely handle zero-magnitude vectors (return 0.0, not inf/nan)
"""

from __future__ import annotations

import math
from typing import List, Optional

from app.embedding.validation import EmbeddingValidationError, validate_vector


def cosine_similarity(
    a: List[float],
    b: List[float],
    *,
    validate: bool = True,
) -> float:
    """
    Compute cosine similarity between two vectors.

    Args:
        a: First vector.
        b: Second vector.
        validate: If True, validate vectors before computation.

    Returns:
        Cosine similarity in range [-1.0, 1.0].

    Raises:
        EmbeddingValidationError: If vectors are invalid and validate=True.
    """
    if validate:
        a = validate_vector(a)
        b = validate_vector(b)

    if len(a) != len(b):
        raise EmbeddingValidationError(
            f"Dimension mismatch: expected {len(b)}, got {len(a)}"
        )

    if len(a) == 0:
        return 0.0

    # Compute dot product
    dot = sum(x * y for x, y in zip(a, b))

    # Compute magnitudes
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(y * y for y in b))

    # Handle zero-magnitude vectors
    if mag_a == 0.0 or mag_b == 0.0:
        return 0.0

    similarity = dot / (mag_a * mag_b)

    # Clamp to [-1, 1] for floating-point safety
    if similarity > 1.0:
        return 1.0
    if similarity < -1.0:
        return -1.0
    return similarity