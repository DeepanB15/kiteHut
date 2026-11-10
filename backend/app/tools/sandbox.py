"""
Sandbox and Security Validators for Tool Execution.

Enforces:
1. Path confinement (no directory traversal outside repository workspace).
2. Command safety (rejects destructive, catastrophic, or uncontrolled commands).
"""

from pathlib import Path
import re
from typing import Optional


class SecurityViolationError(Exception):
    """Raised when an operation violates sandbox security policies."""


class PathValidator:
    """Validates and confines file system operations within repository boundaries."""

    @staticmethod
    def resolve_safe_path(target_path: str, repository_path: str) -> Path:
        """
        Resolves a target path against the repository workspace root.
        Ensures the path does not escape the repository boundary.
        """
        repo_root = Path(repository_path).resolve()
        candidate = Path(target_path)

        if not candidate.is_absolute():
            resolved = (repo_root / candidate).resolve()
        else:
            resolved = candidate.resolve()

        # Check if resolved path is strictly within repo_root
        try:
            resolved.relative_to(repo_root)
        except ValueError:
            raise SecurityViolationError(
                f"Path traversal detected: '{target_path}' is outside repository '{repo_root}'"
            )

        return resolved


class CommandValidator:
    """Inspects shell commands to prevent catastrophic operations."""

    # Blacklist of catastrophic commands
    DANGEROUS_PATTERNS = [
        r"\brm\s+(-[rfRF]+\s+)?(/|/root|/bin|/usr|/etc|C:\\Windows|C:\\)",
        r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:",  # Fork bomb
        r"\bmkfs\b",
        r"\bdd\s+if=.*\sof=/dev/[a-z]+",
        r"\bcurl\s+.*\|\s*(sh|bash)\b",
        r"\bwget\s+.*\|\s*(sh|bash)\b",
        r"\bshutdown\b",
        r"\breboot\b",
        r"\bformat\s+[c-zC-Z]:",
    ]

    @classmethod
    def validate_command(cls, command: str) -> None:
        """
        Validate shell command against dangerous patterns.
        Raises SecurityViolationError if a dangerous pattern is detected.
        """
        if not command or not command.strip():
            raise SecurityViolationError("Empty command is not allowed.")

        cmd_clean = command.strip()

        for pattern in cls.DANGEROUS_PATTERNS:
            if re.search(pattern, cmd_clean, re.IGNORECASE):
                raise SecurityViolationError(
                    f"Command blocked by safety policy: matched dangerous pattern '{pattern}'"
                )
