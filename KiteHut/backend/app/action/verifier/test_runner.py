"""
Test Runner and Sandbox Execution Verifier for RepoLens Action Engine.
"""

from pathlib import Path
import subprocess
import sys
import time
from typing import List, Optional

from app.action.models.patch import TestExecutionResult


class TestRunner:
    """Executes workspace test commands and verifies that patches introduce no regressions."""

    __test__ = False  # Prevent pytest from collecting as test suite

    def __init__(self, repository_path: str):
        self.root = Path(repository_path).resolve()

    def run_tests(
        self,
        test_paths: Optional[List[str]] = None,
        timeout_seconds: int = 60,
    ) -> TestExecutionResult:
        """Run tests via pytest in the repository workspace."""
        start_time = time.time()
        # Find Python interpreter
        py_exe = sys.executable

        # Build pytest command
        cmd = [py_exe, "-m", "pytest", "-q", "--no-header"]
        if test_paths:
            cmd.extend(test_paths)

        try:
            result = subprocess.run(
                cmd,
                cwd=str(self.root),
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
            )

            duration = round((time.time() - start_time) * 1000, 2)
            passed = result.returncode == 0
            output = result.stdout + "\n" + result.stderr

            return TestExecutionResult(
                passed=passed,
                output=output.strip(),
                error_message=None if passed else f"Test run exited with status {result.returncode}",
                duration_ms=duration,
            )
        except subprocess.TimeoutExpired:
            return TestExecutionResult(
                passed=False,
                output="Test execution timed out.",
                error_message=f"Timed out after {timeout_seconds}s",
                duration_ms=round((time.time() - start_time) * 1000, 2),
            )
        except Exception as error:
            return TestExecutionResult(
                passed=False,
                output=str(error),
                error_message=str(error),
                duration_ms=round((time.time() - start_time) * 1000, 2),
            )
