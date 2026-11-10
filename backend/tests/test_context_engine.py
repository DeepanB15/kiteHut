"""
Unit and Integration Tests for Context Engine Subsystem.
"""

from pathlib import Path
from app.context.code.ast_analyzer import ASTCodeAnalyzer, SymbolType
from app.context.code.import_analyzer import ImportAnalyzer
from app.context.code.symbol_index import SymbolIndex
from app.context.git.git_context import GitContextExtractor
from app.context.project_map.project_map import ProjectMapBuilder
from app.context.repository.repo_inspector import RepoInspector
from app.context.repository.tech_detector import TechDetector
from app.context.retrieval.snippet_retriever import SnippetRetriever


def test_repo_inspector_and_tech_detector(temp_workspace):
    """Verify filesystem scanning, language detection, and framework identification."""
    ws = temp_workspace
    (ws / "requirements.txt").write_text("fastapi>=0.100.0\npytest>=7.0.0\n", encoding="utf-8")
    tests_dir = ws / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)
    (tests_dir / "test_main.py").write_text("def test_dummy():\n    assert True\n", encoding="utf-8")

    inspector = RepoInspector(str(ws))
    structure = inspector.inspect()

    assert structure.total_files >= 4
    assert "Python" in structure.languages
    assert structure.primary_language == "Python"
    assert any("requirements.txt" in m for m in structure.manifest_files)

    # Tech detector
    detector = TechDetector(str(ws))
    detected = detector.detect()
    detected_names = [d.name for d in detected]

    assert "FastAPI" in detected_names
    assert "pytest" in detected_names

    entry_points = detector.find_entry_points()
    assert "src/main.py" in entry_points


def test_ast_code_analyzer_python():
    """Verify AST symbol extraction for classes, functions, and routes."""
    code = """
import os
from fastapi import APIRouter

router = APIRouter()

class UserService:
    \"\"\"Service managing user accounts.\"\"\"
    def __init__(self, db_session):
        self.db = db_session

    async def get_user_by_id(self, user_id: int) -> dict:
        if user_id <= 0:
            raise ValueError("Invalid user ID")
        return {"id": user_id, "name": "Alice"}

@router.get("/users/{user_id}")
async def fetch_user(user_id: int):
    \"\"\"Fetch user endpoint.\"\"\"
    return {"status": "ok"}
"""
    analyzer = ASTCodeAnalyzer()
    symbols = analyzer.parse_file("app/services/user.py", code)

    sym_names = {s.name: s for s in symbols}
    assert "UserService" in sym_names
    assert sym_names["UserService"].symbol_type == SymbolType.CLASS
    assert sym_names["UserService"].docstring == "Service managing user accounts."

    assert "get_user_by_id" in sym_names
    assert sym_names["get_user_by_id"].symbol_type == SymbolType.ASYNC_METHOD
    assert sym_names["get_user_by_id"].parent_symbol == "UserService"

    assert "fetch_user" in sym_names
    assert sym_names["fetch_user"].symbol_type == SymbolType.ROUTE_ENDPOINT


def test_import_analyzer_and_circular_detection(temp_workspace):
    """Verify dependency graph construction and circular import cycle discovery."""
    ws = temp_workspace
    mod_a = ws / "src" / "module_a.py"
    mod_b = ws / "src" / "module_b.py"

    # Create circular import: module_a <-> module_b
    mod_a.write_text("from src.module_b import func_b\ndef func_a(): pass\n", encoding="utf-8")
    mod_b.write_text("from src.module_a import func_a\ndef func_b(): pass\n", encoding="utf-8")

    contents = {
        "src/module_a.py": mod_a.read_text(encoding="utf-8"),
        "src/module_b.py": mod_b.read_text(encoding="utf-8"),
    }

    analyzer = ImportAnalyzer(str(ws))
    graph = analyzer.build_graph(contents)

    assert "src/module_a.py" in graph.dependencies
    assert "src/module_b.py" in graph.dependencies["src/module_a.py"]

    assert len(graph.circular_dependencies) > 0
    cycle_nodes = graph.circular_dependencies[0].cycle
    assert "src/module_a.py" in cycle_nodes
    assert "src/module_b.py" in cycle_nodes


def test_symbol_index_and_snippet_retriever(temp_workspace):
    """Verify symbol queries and snippet retrieval."""
    ws = temp_workspace
    code_file = ws / "src" / "calc.py"
    code_file.write_text(
        "class Calculator:\n"
        "    def add(self, a, b):\n"
        "        return a + b\n"
        "    def multiply(self, a, b):\n"
        "        return a * b\n",
        encoding="utf-8",
    )

    analyzer = ASTCodeAnalyzer()
    syms = analyzer.parse_file("src/calc.py", code_file.read_text(encoding="utf-8"))

    index = SymbolIndex(symbols=syms)
    found_calc = index.find_by_name("Calculator")
    assert len(found_calc) == 1
    assert found_calc[0].symbol_type == SymbolType.CLASS

    search_res = index.search_symbols("mult")
    assert len(search_res) == 1
    assert search_res[0].name == "multiply"

    # Snippet retriever
    retriever = SnippetRetriever(str(ws), symbol_index=index)
    snippets = retriever.retrieve_for_symbol("Calculator")
    assert len(snippets) == 1
    assert "class Calculator:" in snippets[0].content


def test_git_context_extractor(temp_git_repo):
    """Verify git status and diff hunk extraction on an active repo."""
    ws = temp_git_repo
    repo_root = Path(ws)

    # Modify main.py and create an untracked file
    main_p = repo_root / "src" / "main.py"
    main_p.write_text(main_p.read_text(encoding="utf-8") + "\n# Extra line\n", encoding="utf-8")
    untracked_p = repo_root / "src" / "new_file.py"
    untracked_p.write_text("# new file\n", encoding="utf-8")

    extractor = GitContextExtractor(str(ws))
    ctx = extractor.extract()

    assert ctx.is_git_repo is True
    assert ctx.is_dirty is True
    assert any(cf.file_path == "src/main.py" for cf in ctx.changed_files)
    assert any(cf.file_path == "src/new_file.py" for cf in ctx.changed_files)
