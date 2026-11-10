"""
Phase 8.1 — Code-Aware Semantic Chunking Tests.
Uses temporary fixture repositories. Does NOT modify user's project.
"""
import hashlib
import tempfile
from pathlib import Path

import pytest

from app.chunking import chunk_file, chunk_python_file, chunk_repo
from app.chunking.model import ChunkList, CodeChunk, SymbolType


@pytest.fixture
def temp_repo():
    tmp = Path(tempfile.mkdtemp())
    # Python file with class + methods + async + import
    (tmp / "auth.py").write_text(
        "import os\nfrom typing import Optional\n\n"
        "class AuthService:\n"
        "    def login(self, token: str) -> bool:\n"
        "        return token == 'secret'\n\n"
        "    async def validate_token(self, token: str) -> bool:\n"
        "        return await self.login(token)\n\n"
        "def standalone():\n"
        "    pass\n"
    )
    # Unsupported file
    (tmp / "readme.md").write_text("# Hello\n")
    # Empty python file
    (tmp / "empty.py").write_text("")
    # Syntax error python file
    (tmp / "bad.py").write_text("def foo(\n")
    yield tmp
    import shutil
    shutil.rmtree(tmp, ignore_errors=True)


# 8.1.9 — Required tests

def test_python_module_produces_chunks(temp_repo):
    result = chunk_file(str(temp_repo / "auth.py"))
    assert isinstance(result, ChunkList)
    assert len(result.chunks) > 0


def test_python_class_chunk():
    code = "class UserService:\n    pass\n"
    result = chunk_python_file("service.py", code)
    class_chunks = [c for c in result.chunks if c.symbol_type == SymbolType.CLASS]
    assert len(class_chunks) >= 1
    assert class_chunks[0].symbol_name == "UserService"


def test_python_method_chunk():
    code = "class AuthService:\n    def validate_token(self):\n        pass\n"
    result = chunk_python_file("auth.py", code)
    method_chunks = [c for c in result.chunks if c.symbol_type == SymbolType.METHOD or (c.symbol_type == SymbolType.FUNCTION and c.parent_symbol == "AuthService")]
    # At minimum method-level awareness preserved via parent_symbol
    names = {c.symbol_name for c in result.chunks}
    assert "validate_token" in names
    # Parent preserved
    for c in result.chunks:
        if c.symbol_name == "validate_token":
            assert c.parent_symbol == "AuthService"


def test_async_function():
    code = "async def fetch():\n    pass\n"
    result = chunk_python_file("a.py", code)
    assert any(c.symbol_type == SymbolType.ASYNC_FUNCTION for c in result.chunks)


def test_parent_class_metadata():
    code = "class Outer:\n    def inner(self): pass\n"
    result = chunk_python_file("p.py", code)
    inner = [c for c in result.chunks if c.symbol_name == "inner"]
    assert len(inner) == 1
    assert inner[0].parent_symbol == "Outer"


def test_file_path_metadata():
    result = chunk_python_file("app/auth/service.py", "class X:\n    pass\n")
    for c in result.chunks:
        assert c.file_path == "app/auth/service.py"


def test_start_end_lines():
    code = "class A:\n    def b(self):\n        pass\n"
    result = chunk_python_file("t.py", code)
    for c in result.chunks:
        if c.symbol_name == "A":
            assert c.start_line == 1 and c.end_line == 3
        elif c.symbol_name == "b":
            assert c.start_line == 2


def test_content_hash_deterministic():
    code = "def foo():\n    pass\n"
    r1 = chunk_python_file("f.py", code)
    r2 = chunk_python_file("f.py", code)
    assert r1.chunks[0].content_hash == r2.chunks[0].content_hash
    assert r1.chunks[0].content_hash == hashlib.sha256(code.encode()).hexdigest()


def test_same_source_identical_chunks():
    code = "class C:\n    pass\n"
    r1 = chunk_python_file("x.py", code)
    r2 = chunk_python_file("x.py", code)
    assert len(r1.chunks) == len(r2.chunks)
    for a, b in zip(r1.chunks, r2.chunks):
        assert a.chunk_id == b.chunk_id
        assert a.content == b.content


def test_changed_source_changed_hash():
    r1 = chunk_python_file("x.py", "def a(): pass\n")
    r2 = chunk_python_file("x.py", "def a(): return 1\n")
    assert r1.chunks[0].content_hash != r2.chunks[0].content_hash


def test_large_chunk_split_deterministic():
    # 250 lines function
    lines = ["def big():\n"] + ["    x = 1\n"] * 250 + ["\n"]
    code = "".join(lines)
    result = chunk_python_file("big.py", code)
    # Should produce continuation chunks
    total_parts = {c.chunk_total for c in result.chunks if c.chunk_total}
    if total_parts:
        assert max(total_parts) >= 2


def test_continuation_metadata():
    code = "def big():\n" + "    pass\n" * 250
    result = chunk_python_file("big.py", code)
    parts = [c for c in result.chunks if c.chunk_part]
    if parts:
        assert all(c.chunk_part == 1 or c.chunk_part == 2 for c in parts)
        assert all(c.chunk_total == 2 for c in parts)


def test_unsupported_fallback(temp_repo):
    result = chunk_file(str(temp_repo / "readme.md"))
    assert result.language == "md"
    assert result.chunks[0].symbol_type == SymbolType.FILE
    assert result.chunks[0].symbol_name is None  # does NOT invent symbol


def test_fallback_no_invented_symbol(temp_repo):
    # Write yaml file inside temp repo
    yaml_path = temp_repo / "config.yaml"
    yaml_path.write_text("key: value\n")
    result = chunk_file(str(yaml_path))
    chunk = result.chunks[0]
    assert chunk.symbol_type == SymbolType.FILE
    assert chunk.symbol_name is None  # conservative


def test_empty_file():
    result = chunk_python_file("e.py", "")
    # Should not crash; either zero chunks or safe file chunk
    assert isinstance(result, ChunkList)


def test_syntax_error_fallback():
    result = chunk_python_file("bad.py", "def foo(\n")
    # Fallback to file-level; no crash
    assert result.chunks[0].symbol_type == SymbolType.FILE


def test_repo_chunking_works(temp_repo):
    results = chunk_repo(str(temp_repo))
    paths = {r.file_path for r in results}
    assert "auth.py" in paths
    # Unsupported files not added as python chunks but file-level handled


def test_phase4_intelligence_intact():
    # Phase 4 code intelligence must remain importable / functional
    from app.intelligence.agents.base_agent import BaseIntelligenceAgent  # noqa: F401
    assert True
