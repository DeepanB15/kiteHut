"""
Phase 8.1 — Code-Aware Semantic Chunk Model.

Deterministic chunk representation with metadata for Phase 8.2 embeddings.
No embeddings, vector DB, or search implemented yet.
"""
from __future__ import annotations

import hashlib
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class SymbolType(str, Enum):
    MODULE = "module"
    CLASS = "class"
    FUNCTION = "function"
    ASYNC_FUNCTION = "async_function"
    METHOD = "method"
    IMPORT = "import"
    FILE = "file"  # conservative fallback for unsupported languages


class CodeChunk(BaseModel):
    """A deterministic semantic chunk of repository source."""

    chunk_id: str  # deterministic (hash-derived, never a UUID)
    file_path: str
    language: str  # "python", "unknown", file extension, ...
    symbol_name: Optional[str] = None
    symbol_type: SymbolType = SymbolType.FILE
    parent_symbol: Optional[str] = None
    start_line: int = 1
    end_line: int = 1
    content: str
    content_hash: str = Field(default="", description="SHA-256 of content")
    metadata: Dict[str, Any] = Field(default_factory=dict)

    # Large-chunk continuation metadata (Phase 8.1.5)
    chunk_part: Optional[int] = None
    chunk_total: Optional[int] = None

    @staticmethod
    def compute_hash(content: str) -> str:
        """SHA-256 content hash used for staleness detection and incremental indexing."""
        return hashlib.sha256(content.encode("utf-8")).hexdigest()


class ChunkMetadata(BaseModel):
    """Extensible metadata preserved for Phase 8.2."""

    module: Optional[str] = None
    imports: List[str] = Field(default_factory=list)
    class_name: Optional[str] = None
    function_name: Optional[str] = None
    decorators: List[str] = Field(default_factory=list)
    docstring: Optional[str] = None
    repository_path: Optional[str] = None


class ChunkList(BaseModel):
    """Ordered, deterministic list of chunks from a file or repository.

    Deliberately carries no timestamp — the same input must produce a
    byte-identical ChunkList.
    """

    chunks: List[CodeChunk] = Field(default_factory=list)
    file_path: Optional[str] = None
    language: str = "unknown"
