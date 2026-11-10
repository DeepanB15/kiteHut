"""
Phase 8.1 — Code-Aware Semantic Chunking.

Deterministic conversion of repository source files into semantic chunks
with stable hashes and metadata. No embeddings or search yet (Phase 8.2).
"""
from .model import CodeChunk, ChunkList, ChunkMetadata, SymbolType
from .python_chunker import chunk_python_file
from .repository_chunker import chunk_file, chunk_repo

__all__ = [
    "CodeChunk",
    "ChunkList",
    "ChunkMetadata",
    "SymbolType",
    "chunk_python_file",
    "chunk_file",
    "chunk_repo",
]
