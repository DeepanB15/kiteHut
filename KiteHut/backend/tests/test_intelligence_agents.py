"""
Unit tests for all 8 Specialist Intelligence Agents.
"""

from pathlib import Path
from app.context.code.ast_analyzer import ASTCodeAnalyzer
from app.context.code.import_analyzer import ImportAnalyzer
from app.context.code.symbol_index import SymbolIndex
from app.context.git.git_context import ChangedFile, GitDiffHunk, GitWorkspaceContext
from app.context.project_map.project_map import ProjectMapBuilder
from app.intelligence.agents.api_agent import APIAgent
from app.intelligence.agents.architecture_agent import ArchitectureAgent
from app.intelligence.agents.code_review_agent import CodeReviewAgent
from app.intelligence.agents.configuration_agent import ConfigurationAgent
from app.intelligence.agents.dependency_agent import DependencyAgent
from app.intelligence.agents.quality_agent import QualityAgent
from app.intelligence.agents.security_agent import SecurityAgent
from app.intelligence.agents.testing_agent import TestingAgent
from app.intelligence.models.findings import FindingCategory, FindingSeverity


def test_security_agent_detects_secrets_and_sqli(temp_workspace):
    """Verify security agent flags hardcoded keys and SQL injection vulnerabilities."""
    ws = temp_workspace
    vuln_file = ws / "src" / "vuln.py"
    vuln_file.write_text(
        "import os\n"
        "api_key = 'sk_live_1234567890abcdef'\n"
        "def query_user(cursor, user_id):\n"
        "    cursor.execute(f'SELECT * FROM users WHERE id = {user_id}')\n"
        "    os.system(f'echo {user_id}')\n",
        encoding="utf-8",
    )

    builder = ProjectMapBuilder(str(ws))
    pmap, sym_index, graph = builder.build()

    agent = SecurityAgent(llm_provider=None)
    result = agent.analyze(project_map=pmap, symbol_index=sym_index, import_graph=graph)

    assert result.category == FindingCategory.SECURITY
    assert len(result.findings) >= 2
    titles = [f.title for f in result.findings]
    assert any("secret" in t.lower() or "credential" in t.lower() for t in titles)
    assert any("sql injection" in t.lower() for t in titles)


def test_configuration_agent_missing_env_example(temp_workspace):
    """Verify configuration agent detects undocumented env variables."""
    ws = temp_workspace
    cfg_file = ws / "src" / "config.py"
    cfg_file.write_text(
        "import os\n"
        "STRIPE_KEY = os.getenv('STRIPE_API_SECRET')\n"
        "DB_PASS = os.environ.get('DATABASE_PASSWORD')\n",
        encoding="utf-8",
    )

    builder = ProjectMapBuilder(str(ws))
    pmap, sym_index, graph = builder.build()

    agent = ConfigurationAgent(llm_provider=None)
    result = agent.analyze(project_map=pmap, symbol_index=sym_index, import_graph=graph)

    assert len(result.findings) > 0
    assert any("env.example" in f.title.lower() or "undocumented" in f.title.lower() for f in result.findings)


def test_api_agent_detects_untested_and_undocumented_routes(temp_workspace):
    """Verify API agent flags route definitions."""
    ws = temp_workspace
    api_file = ws / "src" / "api.py"
    api_file.write_text(
        "from fastapi import APIRouter\n"
        "router = APIRouter()\n"
        "@router.post('/items')\n"
        "def create_item(data: dict):\n"
        "    return data\n",
        encoding="utf-8",
    )

    builder = ProjectMapBuilder(str(ws))
    pmap, sym_index, graph = builder.build()

    agent = APIAgent(llm_provider=None)
    result = agent.analyze(project_map=pmap, symbol_index=sym_index, import_graph=graph)

    assert len(result.findings) >= 1
    assert any("undocumented" in f.title.lower() or "error handling" in f.title.lower() for f in result.findings)


def test_quality_agent_cyclomatic_complexity(temp_workspace):
    """Verify quality agent flags complex branching logic."""
    ws = temp_workspace
    complex_file = ws / "src" / "logic.py"
    complex_file.write_text(
        "def complex_flow(x, y, z):\n"
        "    if x > 0:\n"
        "        if y > 0:\n"
        "            if z > 0:\n"
        "                return 1\n"
        "            elif z == 0:\n"
        "                return 2\n"
        "        elif y == 0:\n"
        "            return 3\n"
        "    elif x == 0:\n"
        "        for i in range(10):\n"
        "            if i % 2 == 0 or i % 3 == 0 or i % 5 == 0:\n"
        "                while y > 0:\n"
        "                    y -= 1\n"
        "    return 0\n",
        encoding="utf-8",
    )

    builder = ProjectMapBuilder(str(ws))
    pmap, sym_index, graph = builder.build()

    agent = QualityAgent(llm_provider=None)
    result = agent.analyze(project_map=pmap, symbol_index=sym_index, import_graph=graph)

    assert any("complexity" in f.title.lower() for f in result.findings)


def test_code_review_agent_diff_inspection(temp_workspace):
    """Verify code review agent spots debug statements in git diff hunks."""
    builder = ProjectMapBuilder(str(temp_workspace))
    pmap, sym_index, graph = builder.build()

    git_ctx = GitWorkspaceContext(
        is_git_repo=True,
        changed_files=[
            ChangedFile(
                file_path="src/main.py",
                status="modified",
                insertions=2,
                deletions=0,
                hunks=[
                    GitDiffHunk(
                        old_start=1,
                        old_lines=5,
                        new_start=1,
                        new_lines=7,
                        lines=[
                            " def compute():",
                            "+    print('DEBUG: temp value')",
                            "+    breakpoint()",
                            "     return 42",
                        ],
                    )
                ],
            )
        ],
    )

    agent = CodeReviewAgent(llm_provider=None)
    result = agent.analyze(project_map=pmap, symbol_index=sym_index, import_graph=graph, git_context=git_ctx)

    assert len(result.findings) >= 2
    titles = [f.title for f in result.findings]
    assert any("print" in t.lower() for t in titles)
    assert any("breakpoint" in t.lower() for t in titles)
