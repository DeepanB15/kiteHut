"""
Phase 4 — Code Intelligence Tests (deterministic, no LLM dependency).
Uses native Python `ast` (not broken tree-sitter binding).
"""

import tempfile, shutil
from pathlib import Path
import pytest


# ------------------------------------------------------------------
# Engine
# ------------------------------------------------------------------

def test_intelligence_engine_scans_py_file():
    from app.context.code.intelligence_engine import CodeIntelligenceEngine

    ws = Path(tempfile.mkdtemp())
    (ws / "auth.py").write_text("def authenticate(x):\n    pass\nclass AuthHandler:\n    pass\n")
    engine = CodeIntelligenceEngine(str(ws))
    scan = engine.scan()
    assert scan["files_scanned"] == 1
    assert scan["languages"] == [".py"]
    assert scan["symbol_count"] >= 2
    shutil.rmtree(ws)


def test_intelligence_engine_find_symbol():
    from app.context.code.intelligence_engine import CodeIntelligenceEngine

    ws = Path(tempfile.mkdtemp())
    (ws / "main.py").write_text("def main(): pass")
    engine = CodeIntelligenceEngine(str(ws))
    engine.scan()
    syms = engine.find_symbol("main")
    assert len(syms) == 1
    assert syms[0].name == "main"
    shutil.rmtree(ws)


def test_intelligence_engine_empty_repo():
    from app.context.code.intelligence_engine import CodeIntelligenceEngine

    ws = Path(tempfile.mkdtemp())
    engine = CodeIntelligenceEngine(str(ws))
    scan = engine.scan()
    assert scan["files_scanned"] == 0
    assert scan["symbol_count"] == 0
    shutil.rmtree(ws)


# ------------------------------------------------------------------
# Symbol index (existing code)
# ------------------------------------------------------------------

def test_symbol_index_exists():
    from app.context.code.symbol_index import SymbolIndex

    assert SymbolIndex is not None


def test_ast_analyzer_python():
    from app.context.code.ast_analyzer import ASTCodeAnalyzer, SymbolType

    analyzer = ASTCodeAnalyzer()
    syms = analyzer.parse_file("test.py", "def foo():\n    pass\n")
    assert any(s.name == "foo" and s.symbol_type == SymbolType.FUNCTION for s in syms)


# ------------------------------------------------------------------
# Integration: agent + code intelligence
# ------------------------------------------------------------------

def test_agent_imports_intelligence():
    from app.agent.investigate import InvestigationResult
    from app.context.code.intelligence_engine import CodeIntelligenceEngine

    # Just confirm both import cleanly; full reasoning requires LLM.
    assert InvestigationResult is not None
    assert CodeIntelligenceEngine is not None
