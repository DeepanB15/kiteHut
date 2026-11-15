"""
Repository Path Containment Guard.

Patch targets and rollback targets are always expressed as paths relative to a
repository root. This module resolves such paths while guaranteeing the final
destination (after symlink resolution) stays inside that root.
"""

import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
from typing import Union


class PathContainmentError(ValueError):
    """Raised when a repository-relative path would escape the repository root."""


_WINDOWS_DRIVE = re.compile(r"^[A-Za-z]:")


def resolve_repository_path(
    repository_root: Union[str, Path],
    relative_path: str,
) -> Path:
    """
    Resolve ``relative_path`` against ``repository_root`` and confine the result.

    Rejects:
    - empty targets
    - absolute paths (POSIX, Windows drive-letter, UNC) outside the root
    - any ``..`` path component (traversal)
    - targets whose resolved destination (including symlinks) escapes the root

    Returns the fully resolved absolute path, which is guaranteed to be a strict
    descendant of the resolved repository root.
    """
    root = Path(repository_root).resolve()

    if not isinstance(relative_path, str) or not relative_path.strip():
        raise PathContainmentError("Patch target path must be a non-empty string.")

    # Normalize separators so Windows-style paths cannot bypass component checks.
    normalized = relative_path.strip().replace("\\", "/")

    # Absolute targets are never valid patch targets: reject POSIX roots/UNC
    # prefixes, Windows drive-letter paths (including drive-relative "C:foo")
    # and anything the platform itself considers absolute.
    if (
        normalized.startswith("/")
        or _WINDOWS_DRIVE.match(normalized)
        or PurePosixPath(normalized).is_absolute()
        or PureWindowsPath(normalized).is_absolute()
        or Path(normalized).is_absolute()
    ):
        raise PathContainmentError(
            f"Absolute patch target is not allowed: '{relative_path}'"
        )

    parts = [part for part in normalized.split("/") if part not in ("", ".")]
    if not parts:
        raise PathContainmentError(
            f"Patch target does not point to a file: '{relative_path}'"
        )
    if any(part == ".." for part in parts):
        raise PathContainmentError(
            f"Path traversal ('..') is not allowed in patch target: '{relative_path}'"
        )

    candidate = root.joinpath(*parts)
    # resolve() follows symlinks (and resolves existing parent segments for
    # paths that do not exist yet), so a symlinked escape is caught here.
    resolved = candidate.resolve()

    root_key = os.path.normcase(str(root))
    resolved_key = os.path.normcase(str(resolved))
    if resolved_key == root_key or not resolved_key.startswith(root_key + os.sep):
        raise PathContainmentError(
            f"Patch target escapes repository root: '{relative_path}' -> '{resolved}'"
        )

    return resolved
