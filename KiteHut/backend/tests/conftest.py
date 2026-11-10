"""
Pytest configuration and shared fixtures for RepoLens test suite.
"""

import os
from pathlib import Path
import shutil
import tempfile
import pytest
from git import Repo

# Ensure backend root is on sys.path
import sys
backend_root = Path(__file__).parent.parent
if str(backend_root) not in sys.path:
    sys.path.insert(0, str(backend_root))


@pytest.fixture
def temp_workspace():
    """Create a temporary directory simulating a repository workspace."""
    temp_dir = tempfile.mkdtemp(prefix="repolens_test_ws_")
    ws_path = Path(temp_dir).resolve()

    # Create sample files
    src_dir = ws_path / "src"
    src_dir.mkdir(parents=True, exist_ok=True)

    main_py = src_dir / "main.py"
    main_py.write_text(
        "def add(a: int, b: int) -> int:\n    return a + b\n\ndef main():\n    print(add(2, 3))\n",
        encoding="utf-8",
    )

    readme = ws_path / "README.md"
    readme.write_text("# Test Repo\nSample repository for testing.\n", encoding="utf-8")

    yield ws_path

    # Teardown
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def temp_git_repo(temp_workspace):
    """Create a temporary git repository with an initial commit."""
    repo = Repo.init(temp_workspace)
    repo.git.add("-A")
    repo.git.config("user.name", "RepoLens Tester")
    repo.git.config("user.email", "test@repolens.local")
    repo.git.commit("-m", "Initial test commit")

    yield temp_workspace
