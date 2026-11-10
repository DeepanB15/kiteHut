"""
Phase 8.3 — Local Vector Index & Semantic Retrieval.

Local brute-force vector index for cosine similarity search over
Phase 8.2 embedding records. No external infrastructure required.
"""

from app.retrieval.local_index import LocalVectorIndex
from app.retrieval.retrieval import VectorRetrieval
from app.retrieval.similarity import cosine_similarity

__all__ = [
    "LocalVectorIndex",
    "VectorRetrieval",
    "cosine_similarity",
]