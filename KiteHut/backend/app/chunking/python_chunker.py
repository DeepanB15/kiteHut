"""
Phase 8.1.2 — Python AST Chunking (deterministic, using stdlib ast).
Reuses existing Phase 4 code intelligence patterns; no Tree-sitter.
"""
from __future__ import annotations

import ast
import hashlib
from pathlib import Path
from typing import List, Optional

from .model import CodeChunk, ChunkList, ChunkMetadata, SymbolType

MAX_CHUNK_LINES = 200


def _hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _chunk_id(file_path: str, start_line: int, symbol_name: Optional[str]) -> str:
    # Deterministic, not UUID-based
    base = f"{file_path}:{start_line}:{symbol_name or 'anon'}"
    return hashlib.sha256(base.encode()).hexdigest()[:24]


def chunk_python_file(file_path: str, content: str) -> ChunkList:
    chunks: List[CodeChunk] = []
    try:
        tree = ast.parse(content)
    except SyntaxError:
        # Phase 8.1.9 — syntax-error fallback
        return ChunkList(
            chunks=[
                CodeChunk(
                    chunk_id=_chunk_id(file_path, 1, None),
                    file_path=file_path,
                    language="python",
                    symbol_name=None,
                    symbol_type=SymbolType.FILE,
                    start_line=1,
                    end_line=len(content.splitlines()) or 1,
                    content=content,
                    content_hash=_hash(content),
                    metadata=ChunkMetadata(module=file_path).model_dump(),
                )
            ],
            file_path=file_path,
            language="python",
        )

    lines = content.splitlines(keepends=True)

    # Module-level imports + docstring as module chunk (optional, minimal)
    module_chunk = _make_module_chunk(file_path, tree, lines, content)
    if module_chunk:
        chunks.append(module_chunk)

    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            chunks.extend(_chunk_node(file_path, node, lines, content, parent=None))

    # If no structural chunks found (empty file / only imports), fallback
    if not chunks and content.strip():
        chunks.append(
            CodeChunk(
                chunk_id=_chunk_id(file_path, 1, None),
                file_path=file_path,
                language="python",
                symbol_type=SymbolType.FILE,
                start_line=1,
                end_line=len(lines) or 1,
                content=content,
                content_hash=_hash(content),
                metadata=ChunkMetadata(module=file_path).model_dump(),
            )
        )

    return ChunkList(chunks=chunks, file_path=file_path, language="python")


def _make_module_chunk(file_path: str, tree: ast.Module, lines: List[str], content: str) -> Optional[CodeChunk]:
    # Minimal module chunk: only if there's meaningful module-level content
    # (keep small; don't duplicate huge class bodies)
    imports = [n for n in ast.iter_child_nodes(tree) if isinstance(n, (ast.Import, ast.ImportFrom))]
    if not imports:
        return None
    # Take first 30 lines max for module context
    module_text = "".join(lines[:30])
    return CodeChunk(
        chunk_id=_chunk_id(file_path, 1, "module"),
        file_path=file_path,
        language="python",
        symbol_name=Path(file_path).stem,
        symbol_type=SymbolType.MODULE,
        start_line=1,
        end_line=min(30, len(lines) or 1),
        content=module_text,
        content_hash=_hash(module_text),
        metadata=ChunkMetadata(
            module=Path(file_path).stem,
            imports=[_import_str(i) for i in imports],
            repository_path=file_path,
        ).model_dump(),
    )


def _import_str(node: ast.AST) -> str:
    if isinstance(node, ast.Import):
        return ", ".join(alias.name for alias in node.names)
    if isinstance(node, ast.ImportFrom):
        mod = node.module or ""
        names = ", ".join(alias.name for alias in node.names)
        return f"from {mod} import {names}" if mod else f"import {names}"
    return ""


def _chunk_node(file_path: str, node: ast.AST, lines: List[str], content: str, parent: Optional[str]) -> List[CodeChunk]:
    result: List[CodeChunk] = []
    name = getattr(node, "name", None)
    symbol_type = SymbolType.CLASS if isinstance(node, ast.ClassDef) else (
        SymbolType.ASYNC_FUNCTION if isinstance(node, ast.AsyncFunctionDef) else SymbolType.FUNCTION
    )
    start = node.lineno
    end = getattr(node, "end_lineno", start) or start

    # Context preservation: include parent class info in metadata, keep chunk bounded
    chunk_text = "".join(lines[start - 1:end])

    # Large chunk handling (Phase 8.1.5)
    line_count = end - start + 1
    if line_count > MAX_CHUNK_LINES:
        # Split deterministically by line blocks
        total = (line_count + MAX_CHUNK_LINES - 1) // MAX_CHUNK_LINES
        for i in range(total):
            s = start + i * MAX_CHUNK_LINES - 1
            e = min(start + (i + 1) * MAX_CHUNK_LINES - 1, end)
            part = "".join(lines[s:e])
            result.append(CodeChunk(
                chunk_id=_chunk_id(file_path, s + 1, name),
                file_path=file_path,
                language="python",
                symbol_name=name,
                symbol_type=symbol_type,
                parent_symbol=parent,
                start_line=s + 1,
                end_line=e,
                content=part,
                content_hash=_hash(part),
                chunk_part=i + 1,
                chunk_total=total,
                metadata=ChunkMetadata(
                    module=Path(file_path).stem,
                    class_name=parent if parent else None,
                    function_name=name if symbol_type != SymbolType.CLASS else None,
                    repository_path=file_path,
                ).model_dump(),
            ))
        return result

    # Normal chunk — include method parent for methods. Methods get METHOD symbol.
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        # Methods inside classes: derive parent from outer class context
        # (simplified — parent already passed in from _chunk_node recursive call)
        if parent is not None:
            symbol_type = SymbolType.METHOD

    # For methods inside classes: derive parent name from enclosing class (simplified)
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and parent is None:
        # We don't have enclosing class easily without walking up; keep metadata conservative
        pass

    meta = ChunkMetadata(
        module=Path(file_path).stem,
        class_name=parent,
        function_name=name if symbol_type != SymbolType.CLASS else None,
        repository_path=file_path,
    ).model_dump()

    # Decorators for methods/functions
    decs = [ast.dump(d) for d in getattr(node, "decorator_list", [])]
    if decs:
        meta["decorators"] = decs

    docstring = ast.get_docstring(node)
    if docstring:
        meta["docstring"] = docstring[:500]

    result.append(CodeChunk(
        chunk_id=_chunk_id(file_path, start, name),
        file_path=file_path,
        language="python",
        symbol_name=name,
        symbol_type=symbol_type,
        parent_symbol=parent,
        start_line=start,
        end_line=end,
        content=chunk_text,
        content_hash=_hash(chunk_text),
        metadata=meta,
    ))

    # Class-level sub-chunks (methods) — preserve parent symbol
    if isinstance(node, ast.ClassDef):
        for sub in ast.iter_child_nodes(node):
            if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                result.extend(_chunk_node(file_path, sub, lines, content, parent=name))

    return result
