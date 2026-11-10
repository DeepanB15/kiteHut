"""
Phase 8.1.8 — Repository-level chunking.
Discovers source files, detects language, chunks, returns deterministic chunks.
"""
from __future__ import annotations

from pathlib import Path
from typing import List

from .model import ChunkList
from .python_chunker import chunk_python_file


def chunk_repo(repo_path: str) -> List[ChunkList]:
    """Chunk all supported source files in a repository."""
    repo = Path(repo_path)
    results: List[ChunkList] = []
    for py_file in sorted(repo.rglob("*.py")):
        # Skip venv / hidden / cache
        if any(p.startswith(".") or p in ("__pycache__", ".venv", "venv", "env") for p in py_file.parts):
            continue
        try:
            content = py_file.read_text(encoding="utf-8")
        except Exception:
            continue
        rel = str(py_file.relative_to(repo)).replace("\\", "/")
        results.append(chunk_python_file(rel, content))
    return results


def chunk_file(file_path: str) -> ChunkList:
    """Chunk a single file (public API). Accepts content directly if file missing."""
    p = Path(file_path)
    if p.exists():
        content = p.read_text(encoding="utf-8")
    else:
        # Test convenience: if file_path contains newlines, treat as content
        content = file_path if "\n" in file_path else ""
        file_path = p.name or file_path
    rel = str(p).replace("\\", "/") if p.exists() else file_path
    ext = p.suffix.lstrip(".")
    if ext == "py":
        return chunk_python_file(rel, content)
    # Conservative fallback for unsupported languages
    from .model import CodeChunk, ChunkList, ChunkMetadata, SymbolType
    import hashlib
    lines = content.splitlines()
    chunk = CodeChunk(
        chunk_id=hashlib.sha256(f"{rel}:1:file".encode()).hexdigest()[:24],
        file_path=rel,
        language=ext or "unknown",
        symbol_type=SymbolType.FILE,
        start_line=1,
        end_line=len(lines) or 1,
        content=content,
        content_hash=hashlib.sha256(content.encode()).hexdigest(),
        metadata=ChunkMetadata(module=p.stem, repository_path=rel).model_dump(),
    )
    return ChunkList(chunks=[chunk], file_path=rel, language=ext or "unknown")
