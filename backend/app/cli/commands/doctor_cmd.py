"""
`kitehut doctor` command.
Performs comprehensive system diagnostics, verifying environment, Git, Ollama, permissions, and dependencies.
"""

import importlib
import os
from pathlib import Path
import sys
import click

from app.cli.ui import (
    bold,
    cyan,
    dim,
    green,
    print_bullet,
    print_error,
    print_header,
    print_info,
    print_success,
    print_warning,
    red,
    yellow,
)
from app.context.git.git_context import GitContextExtractor
from app.llm.factory import create_llm_provider


@click.command(name="doctor")
@click.option(
    "--path",
    "-p",
    "repo_path",
    default=".",
    type=click.Path(exists=True, file_okay=False, dir_okay=True, readable=True),
    help="Target repository directory path.",
)
def doctor_command(repo_path: str):
    """Run comprehensive system diagnostics to ensure KiteHut environment is healthy."""
    root = Path(repo_path).resolve()
    print_header("KiteHut Diagnostics (Doctor)")

    checks_passed = 0
    total_checks = 6

    # 1. Python runtime
    py_ver = sys.version.split()[0]
    if sys.version_info >= (3, 10):
        print_success(f"Python Runtime: v{py_ver} (Supported)")
        checks_passed += 1
    else:
        print_error(f"Python Runtime: v{py_ver} (Requires Python >= 3.10)")

    # 2. Workspace Write Permissions
    try:
        test_file = root / ".kitehut_write_test.tmp"
        test_file.write_text("ok", encoding="utf-8")
        test_file.unlink()
        print_success(f"Workspace Access: Write permissions verified for {root}")
        checks_passed += 1
    except Exception as error:
        print_error(f"Workspace Access: Write failed: {error}")

    # 3. Git Version Control
    git_extractor = GitContextExtractor(str(root))
    git_context = git_extractor.extract()
    if git_context and git_context.is_git_repo:
        print_success(f"Git Repository: Detected valid repo on branch '{git_context.active_branch}'")
        checks_passed += 1
    else:
        print_warning(f"Git Repository: {root} is not a valid Git repository.")

    # 4. Local AI (Ollama)
    try:
        llm = create_llm_provider()
        if hasattr(llm, "is_available") and llm.is_available():
            print_success(f"AI Inference: Ollama online with model '{getattr(llm, 'model', 'ollama')}'")
            checks_passed += 1
        else:
            print_warning("AI Inference: Ollama offline or unreachable at http://localhost:11434")
    except Exception as error:
        print_warning(f"AI Inference: Ollama check failed ({error})")

    # 5. Core Libraries & Dependencies
    required_pkgs = ["fastapi", "pydantic", "git", "langgraph", "click", "colorama"]
    missing_pkgs = []
    for pkg in required_pkgs:
        try:
            importlib.import_module(pkg)
        except ImportError:
            missing_pkgs.append(pkg)

    if not missing_pkgs:
        print_success("Core Dependencies: All required libraries installed")
        checks_passed += 1
    else:
        print_error(f"Core Dependencies: Missing {', '.join(missing_pkgs)}")

    # 6. Database / State Storage
    try:
        from app.core.database import SessionLocal, engine
        with SessionLocal() as session:
            pass
        print_success("Database / Storage: SQLite / ORM operational")
        checks_passed += 1
    except Exception as error:
        print_warning(f"Database / Storage: {error}")

    # Summary
    print("\n" + bold("Doctor Diagnostics Summary:"))
    if checks_passed == total_checks:
        print_success(f"All {checks_passed}/{total_checks} diagnostic checks passed! KiteHut is ready to use.")
    else:
        print_warning(f"{checks_passed}/{total_checks} checks passed. Address warnings/errors for best experience.")
