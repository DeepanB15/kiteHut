"""
Terminal and Test Execution Tools for RepoLens Agent.

Includes:
- run_command (APPROVAL_REQUIRED)
- run_tests (APPROVAL_REQUIRED)
- run_linter (APPROVAL_REQUIRED)
- run_typecheck (APPROVAL_REQUIRED)
"""

import os
from pathlib import Path
import subprocess
import sys
from typing import Any, Dict, Optional

from app.agent.permissions.policies import PermissionType, RiskLevel
from app.tools.base import BaseTool
from app.tools.sandbox import CommandValidator, PathValidator


class RunCommandTool(BaseTool):
    """Tool to execute shell commands within the repository directory."""

    name = "run_command"
    description = "Execute a shell command inside the repository workspace with timeout and security checks."
    permission_type = PermissionType.EXECUTE
    risk_level = RiskLevel.APPROVAL_REQUIRED

    def get_parameter_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Shell command to execute"},
                "cwd": {"type": "string", "description": "Subdirectory to run command in, defaults to repo root"},
                "timeout": {"type": "integer", "description": "Command timeout in seconds (default: 60)"},
                "repository_path": {"type": "string", "description": "Root workspace repository path"},
            },
            "required": ["command", "repository_path"],
        }

    def run(
        self,
        command: str,
        repository_path: str,
        cwd: Optional[str] = None,
        timeout: int = 60,
        **kwargs,
    ) -> str:
        CommandValidator.validate_command(command)

        work_dir = PathValidator.resolve_safe_path(cwd or ".", repository_path)
        if not work_dir.exists():
            raise FileNotFoundError(f"Working directory not found: {cwd}")

        try:
            process = subprocess.run(
                command,
                cwd=str(work_dir),
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
            )

            stdout = process.stdout.strip()
            stderr = process.stderr.strip()
            exit_code = process.returncode

            output_parts = [f"[Exit Code: {exit_code}]"]
            if stdout:
                output_parts.append(f"--- STDOUT ---\n{stdout}")
            if stderr:
                output_parts.append(f"--- STDERR ---\n{stderr}")

            if exit_code != 0 and not stdout and not stderr:
                output_parts.append("Command failed with no output.")

            return "\n\n".join(output_parts)

        except subprocess.TimeoutExpired:
            raise TimeoutError(f"Command timed out after {timeout} seconds: {command}")
        except Exception as error:
            raise RuntimeError(f"Command execution error: {error}")


class RunTestsTool(BaseTool):
    """Tool to run automated test suites."""

    name = "run_tests"
    description = "Run automated tests (e.g. pytest, npm test) in the repository."
    permission_type = PermissionType.EXECUTE
    risk_level = RiskLevel.APPROVAL_REQUIRED

    def get_parameter_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "test_command": {"type": "string", "description": "Optional explicit test command (e.g. 'pytest tests/')"},
                "path": {"type": "string", "description": "Optional specific test file or directory path"},
                "repository_path": {"type": "string", "description": "Root workspace repository path"},
                "timeout": {"type": "integer", "description": "Test timeout in seconds (default: 120)"},
            },
            "required": ["repository_path"],
        }

    def run(
        self,
        repository_path: str,
        test_command: Optional[str] = None,
        path: Optional[str] = None,
        timeout: int = 30,
        **kwargs,
    ) -> str:
        repo_root = Path(repository_path).resolve()
        py_exec = sys.executable

        if test_command:
            cmd = test_command
        else:
            # Auto-detect test command
            if (repo_root / "pytest.ini").exists() or (repo_root / "pyproject.toml").exists() or any(repo_root.glob("test_*.py")):
                cmd = f'"{py_exec}" -m pytest {path}' if path else f'"{py_exec}" -m pytest'
            elif (repo_root / "package.json").exists():
                cmd = f"npm test -- {path}" if path else "npm test"
            elif (repo_root / "Cargo.toml").exists():
                cmd = f"cargo test {path}" if path else "cargo test"
            elif (repo_root / "pom.xml").exists():
                cmd = "mvn test"
            else:
                cmd = f'"{py_exec}" -m pytest {path}' if path else f'"{py_exec}" -m pytest'

        CommandValidator.validate_command(cmd)

        try:
            process = subprocess.run(
                cmd,
                cwd=str(repo_root),
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
            )

            status = "PASSED" if process.returncode == 0 else "FAILED"
            out = process.stdout.strip() or process.stderr.strip()
            return f"=== TEST RUN: {status} (Exit Code: {process.returncode}) ===\nCommand: {cmd}\n\n{out}"

        except subprocess.TimeoutExpired:
            raise TimeoutError(f"Test suite timed out after {timeout} seconds: {cmd}")
        except Exception as error:
            raise RuntimeError(f"Error running tests: {error}")


class RunLinterTool(BaseTool):
    """Tool to run linter checks on the code."""

    name = "run_linter"
    description = "Run a linter (flake8, ruff, eslint, etc.) on the repository."
    permission_type = PermissionType.EXECUTE
    risk_level = RiskLevel.APPROVAL_REQUIRED

    def get_parameter_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "linter_command": {"type": "string", "description": "Optional explicit linter command"},
                "path": {"type": "string", "description": "Target file or directory to lint"},
                "repository_path": {"type": "string", "description": "Root workspace repository path"},
            },
            "required": ["repository_path"],
        }

    def run(
        self,
        repository_path: str,
        linter_command: Optional[str] = None,
        path: Optional[str] = None,
        **kwargs,
    ) -> str:
        repo_root = Path(repository_path).resolve()
        target = path or "."

        if linter_command:
            cmd = linter_command
        else:
            if (repo_root / "package.json").exists():
                cmd = f"npx eslint {target}"
            else:
                cmd = f"ruff check {target}"

        CommandValidator.validate_command(cmd)

        process = subprocess.run(
            cmd,
            cwd=str(repo_root),
            shell=True,
            capture_output=True,
            text=True,
            timeout=60,
        )

        out = process.stdout.strip() or process.stderr.strip() or "No linter issues found."
        return f"=== LINTER RESULTS (Exit: {process.returncode}) ===\n{out}"


class RunTypecheckTool(BaseTool):
    """Tool to run static type checker."""

    name = "run_typecheck"
    description = "Run static type checker (mypy, pyright, tsc) on the repository."
    permission_type = PermissionType.EXECUTE
    risk_level = RiskLevel.APPROVAL_REQUIRED

    def get_parameter_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "typecheck_command": {"type": "string", "description": "Optional explicit typecheck command"},
                "path": {"type": "string", "description": "Target file or directory to typecheck"},
                "repository_path": {"type": "string", "description": "Root workspace repository path"},
            },
            "required": ["repository_path"],
        }

    def run(
        self,
        repository_path: str,
        typecheck_command: Optional[str] = None,
        path: Optional[str] = None,
        **kwargs,
    ) -> str:
        repo_root = Path(repository_path).resolve()
        target = path or "."

        if typecheck_command:
            cmd = typecheck_command
        else:
            if (repo_root / "tsconfig.json").exists():
                cmd = f"npx tsc --noEmit"
            else:
                cmd = f"mypy {target}"

        CommandValidator.validate_command(cmd)

        process = subprocess.run(
            cmd,
            cwd=str(repo_root),
            shell=True,
            capture_output=True,
            text=True,
            timeout=60,
        )

        out = process.stdout.strip() or process.stderr.strip() or "Type check passed with no errors."
        return f"=== TYPECHECK RESULTS (Exit: {process.returncode}) ===\n{out}"
