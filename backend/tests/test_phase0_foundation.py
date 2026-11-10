"""
Phase 0 foundation tests — packaging, console entry point, CLI, MCP integrity.

These tests assert real behavior. A test that merely returns a value is not
accepted as a passing test.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from click.testing import CliRunner

BACKEND_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_ROOT.parent


# ---------------------------------------------------------------------------
# pyproject.toml
# ---------------------------------------------------------------------------

def _load_pyproject() -> dict:
    import tomllib

    pyproject_path = BACKEND_ROOT / "pyproject.toml"
    assert pyproject_path.exists(), "backend/pyproject.toml must exist"
    with pyproject_path.open("rb") as handle:
        return tomllib.load(handle)


def test_pyproject_exists_and_declares_project():
    data = _load_pyproject()
    project = data["project"]
    assert project["name"] == "repolens"
    assert project["version"]
    assert project["description"]


def test_pyproject_declares_build_system():
    data = _load_pyproject()
    assert "build-system" in data
    assert data["build-system"]["build-backend"]
    assert any("setuptools" in req for req in data["build-system"]["requires"])


def test_pyproject_declares_console_entry_point():
    data = _load_pyproject()
    scripts = data["project"]["scripts"]
    assert "repolens" in scripts
    # Entry point must point at the existing Click CLI, not a new implementation.
    assert scripts["repolens"] == "app.cli.main:main"


def test_pyproject_dependencies_cover_requirements_txt():
    """Every runtime dependency in requirements.txt must be declared."""
    data = _load_pyproject()
    declared = {
        dep.split(";")[0].split("[")[0].split("=")[0].split(">")[0].split("<")[0].strip().lower()
        for dep in data["project"]["dependencies"]
    }
    requirements = (BACKEND_ROOT / "requirements.txt").read_text(encoding="utf-8")
    for line in requirements.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        base = line.split(";")[0].split("[")[0].split("=")[0].split(">")[0].split("<")[0].strip().lower()
        assert base in declared, f"requirements.txt dependency '{base}' missing from pyproject"


def test_pyproject_packages_resolve_to_app_package():
    """The existing backend/app package must remain the installed package."""
    data = _load_pyproject()
    include = data["tool"]["setuptools"]["packages"]["find"]["include"]
    assert any(entry.startswith("app") for entry in include)


def test_pyproject_declares_no_unnecessary_heavy_dependencies():
    """Phase 0 must not introduce new infrastructure dependencies."""
    data = _load_pyproject()
    joined = " ".join(data["project"]["dependencies"]).lower()
    for forbidden in ("redis", "docker", "tree-sitter", "tree_sitter", "langchain"):
        assert forbidden not in joined, f"Unexpected dependency introduced: {forbidden}"


# ---------------------------------------------------------------------------
# Package import
# ---------------------------------------------------------------------------

def test_app_package_imports():
    import app

    assert app is not None
    assert Path(app.__file__).resolve().parent == (BACKEND_ROOT / "app").resolve()


def test_cli_main_module_imports_and_exposes_cli():
    from app.cli.main import cli, main

    assert callable(main)
    assert cli is not None
    assert cli.name == "repolens"


def test_python_dash_m_app_entrypoint_runs():
    """`python -m app` must invoke the CLI."""
    result = subprocess.run(
        [sys.executable, "-m", "app", "--help"],
        cwd=str(BACKEND_ROOT),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    assert "RepoLens" in result.stdout


# ---------------------------------------------------------------------------
# Console entry point
# ---------------------------------------------------------------------------

def test_console_script_is_installed():
    """The `repolens` console script must be on PATH after install."""
    script = shutil.which("repolens")
    assert script is not None, "console entry point 'repolens' not found on PATH"


def test_console_script_help_output():
    """`repolens --help` must succeed and describe the CLI."""
    script = shutil.which("repolens")
    assert script is not None
    result = subprocess.run(
        [script, "--help"],
        cwd=str(BACKEND_ROOT),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    assert "Usage: repolens" in result.stdout
    assert "Local AI Engineering Agent" in result.stdout


def test_console_script_version():
    script = shutil.which("repolens")
    assert script is not None
    result = subprocess.run(
        [script, "--version"],
        cwd=str(BACKEND_ROOT),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    assert "2.0.0" in result.stdout


def test_installed_distribution_metadata_matches_pyproject():
    from importlib.metadata import version

    assert version("repolens") == _load_pyproject()["project"]["version"]


# ---------------------------------------------------------------------------
# CLI behavior preserved (Click)
# ---------------------------------------------------------------------------

def test_click_cli_help_lists_all_commands():
    from app.cli.main import cli

    result = CliRunner().invoke(cli, ["--help"])
    assert result.exit_code == 0
    for command in ("init", "status", "review", "findings", "fix", "ask", "report", "git", "github", "doctor", "models", "start"):
        assert command in result.output, f"Command '{command}' missing from CLI help"


def test_click_is_the_active_cli_framework():
    """Click is intentionally retained (Typer migration deferred)."""
    import click

    from app.cli.main import cli

    assert isinstance(cli, click.Group)
    from importlib.metadata import version

    assert version("click")


def test_click_cli_init_runs_end_to_end(temp_workspace):
    from app.cli.main import cli

    result = CliRunner().invoke(cli, ["init", "--path", str(temp_workspace)])
    assert result.exit_code == 0
    assert (temp_workspace / ".repolens.json").exists()


# ---------------------------------------------------------------------------
# MCP integrity preserved from Phase 2
# ---------------------------------------------------------------------------

def test_mcp_server_still_constructs_after_packaging():
    from app.mcp.server import RepoLensMCPServer

    server = RepoLensMCPServer(repository_path=".")
    assert server.get_registered_tool_names()


def test_mcp_discovery_still_lists_prd_tools():
    from app.mcp.server import RepoLensMCPServer

    server = RepoLensMCPServer(repository_path=".")
    names = set(server.get_registered_tool_names())
    for required in (
        "list_files",
        "find_symbol",
        "get_repo_structure",
        "get_dependencies",
        "get_git_diff",
        "get_git_log",
        "run_analysis",
    ):
        assert required in names, f"MCP tool '{required}' missing"


def test_mcp_executes_representative_tool_after_packaging(temp_workspace):
    from app.mcp.server import RepoLensMCPServer

    server = RepoLensMCPServer(repository_path=str(temp_workspace))
    result = server._wrap_tool(server.registry.get("read_file"))(path="README.md")
    assert result["success"] is True
    assert "Test Repo" in result["output"]


# ---------------------------------------------------------------------------
# Import-cycle debt: application still imports cleanly
# ---------------------------------------------------------------------------

def test_no_import_cycle_when_importing_agent_core():
    """The lazily-broken cycle must not resurface as an ImportError."""
    from app.agent.runtime.core import AgentCore

    assert AgentCore is not None


def test_no_import_cycle_when_importing_tool_registry():
    from app.tools.registry import create_default_tool_registry

    assert create_default_tool_registry() is not None


def test_import_cycle_is_documented_as_debt():
    """The cycle must be recorded as architectural debt, not silently ignored."""
    debt_file = BACKEND_ROOT / "app" / "ARCHITECTURAL_DEBT.md"
    assert debt_file.exists(), "Import-cycle debt must be documented"
    content = debt_file.read_text(encoding="utf-8").lower()
    assert "import" in content
    assert "cycle" in content
