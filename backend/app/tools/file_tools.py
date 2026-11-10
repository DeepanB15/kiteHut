"""
File System Tools for RepoLens Agent.

Includes:
- read_file (SAFE)
- write_file (APPROVAL_REQUIRED)
- edit_file (APPROVAL_REQUIRED)
- delete_file (APPROVAL_REQUIRED)
- search_files (SAFE)
- search_code (SAFE)
"""

from pathlib import Path
import re
from typing import Any, Dict, List, Optional

from app.agent.permissions.policies import PermissionType, RiskLevel
from app.services.scanner_service import should_ignore
from app.tools.base import BaseTool
from app.tools.sandbox import PathValidator


class ReadFileTool(BaseTool):
    """Tool to safely read content from a file with optional pagination."""

    name = "read_file"
    description = "Read lines from a file within the repository. Supports optional offset and line limit."
    permission_type = PermissionType.READ
    risk_level = RiskLevel.SAFE

    def get_parameter_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Relative or workspace path to the file"},
                "offset": {"type": "integer", "description": "1-indexed line number to start reading from"},
                "limit": {"type": "integer", "description": "Maximum number of lines to read"},
                "repository_path": {"type": "string", "description": "Root workspace repository path"},
            },
            "required": ["path", "repository_path"],
        }

    def run(
        self,
        path: str,
        repository_path: str,
        offset: Optional[int] = None,
        limit: Optional[int] = None,
        **kwargs,
    ) -> str:
        safe_path = PathValidator.resolve_safe_path(path, repository_path)
        if not safe_path.exists():
            raise FileNotFoundError(f"File not found: {path}")
        if safe_path.is_dir():
            raise IsADirectoryError(f"Target path is a directory, not a file: {path}")

        try:
            with open(safe_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
        except Exception as error:
            raise IOError(f"Failed to read file {path}: {error}")

        total_lines = len(lines)
        start_idx = max(0, (offset - 1)) if offset and offset > 0 else 0
        end_idx = min(total_lines, start_idx + limit) if limit and limit > 0 else total_lines

        selected_lines = lines[start_idx:end_idx]
        formatted = []
        for idx, line in enumerate(selected_lines, start=start_idx + 1):
            formatted.append(f"{idx:6d}\t{line.rstrip()}")

        header = f"=== File: {path} (Lines {start_idx + 1}-{end_idx} of {total_lines}) ===\n"
        return header + "\n".join(formatted)


class WriteFileTool(BaseTool):
    """Tool to create or completely overwrite a file."""

    name = "write_file"
    description = "Write or overwrite content to a file in the repository."
    permission_type = PermissionType.WRITE
    risk_level = RiskLevel.APPROVAL_REQUIRED

    def get_parameter_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Relative or workspace path to the file"},
                "content": {"type": "string", "description": "Full file content to write"},
                "repository_path": {"type": "string", "description": "Root workspace repository path"},
            },
            "required": ["path", "content", "repository_path"],
        }

    def run(self, path: str, content: str, repository_path: str, **kwargs) -> str:
        safe_path = PathValidator.resolve_safe_path(path, repository_path)
        safe_path.parent.mkdir(parents=True, exist_ok=True)

        with open(safe_path, "w", encoding="utf-8") as f:
            f.write(content)

        return f"Successfully wrote {len(content)} characters to {path}"


class EditFileTool(BaseTool):
    """Tool to replace exact text segments in an existing file."""

    name = "edit_file"
    description = "Perform exact string replacement in a file."
    permission_type = PermissionType.WRITE
    risk_level = RiskLevel.APPROVAL_REQUIRED

    def get_parameter_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Relative or workspace path to the file"},
                "old_string": {"type": "string", "description": "Exact text snippet to replace"},
                "new_string": {"type": "string", "description": "New replacement text"},
                "replace_all": {"type": "boolean", "description": "Whether to replace all occurrences"},
                "repository_path": {"type": "string", "description": "Root workspace repository path"},
            },
            "required": ["path", "old_string", "new_string", "repository_path"],
        }

    def run(
        self,
        path: str,
        old_string: str,
        new_string: str,
        repository_path: str,
        replace_all: bool = False,
        **kwargs,
    ) -> str:
        safe_path = PathValidator.resolve_safe_path(path, repository_path)
        if not safe_path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        with open(safe_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()

        count = content.count(old_string)
        if count == 0:
            raise ValueError(f"Target string not found in {path}")
        if count > 1 and not replace_all:
            raise ValueError(
                f"Target string occurs {count} times in {path}. Specify replace_all=True or a more unique string."
            )

        if replace_all:
            new_content = content.replace(old_string, new_string)
        else:
            new_content = content.replace(old_string, new_string, 1)

        with open(safe_path, "w", encoding="utf-8") as f:
            f.write(new_content)

        return f"Successfully updated {path} ({count if replace_all else 1} occurrence(s) replaced)"


class DeleteFileTool(BaseTool):
    """Tool to remove a file from the repository."""

    name = "delete_file"
    description = "Delete a file from the repository."
    permission_type = PermissionType.WRITE
    risk_level = RiskLevel.APPROVAL_REQUIRED

    def get_parameter_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Relative or workspace path to the file to delete"},
                "repository_path": {"type": "string", "description": "Root workspace repository path"},
            },
            "required": ["path", "repository_path"],
        }

    def run(self, path: str, repository_path: str, **kwargs) -> str:
        safe_path = PathValidator.resolve_safe_path(path, repository_path)
        if not safe_path.exists():
            raise FileNotFoundError(f"File not found: {path}")
        if safe_path.is_dir():
            raise IsADirectoryError(f"Cannot delete directory using delete_file: {path}")

        safe_path.unlink()
        return f"Successfully deleted file: {path}"


class SearchFilesTool(BaseTool):
    """Tool to search for files matching a glob pattern."""

    name = "search_files"
    description = "Find files in the repository matching a glob pattern (e.g. '**/*.py', 'src/*.ts')."
    permission_type = PermissionType.READ
    risk_level = RiskLevel.SAFE

    def get_parameter_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Glob pattern (e.g. '**/*.py')"},
                "path": {"type": "string", "description": "Subdirectory to search in, defaults to '.'"},
                "repository_path": {"type": "string", "description": "Root workspace repository path"},
            },
            "required": ["pattern", "repository_path"],
        }

    def run(
        self,
        pattern: str,
        repository_path: str,
        path: str = ".",
        **kwargs,
    ) -> str:
        base_dir = PathValidator.resolve_safe_path(path, repository_path)
        if not base_dir.exists():
            raise FileNotFoundError(f"Search directory not found: {path}")

        repo_root = Path(repository_path).resolve()
        matches: List[str] = []

        for p in base_dir.glob(pattern):
            if not should_ignore(p):
                try:
                    rel = p.relative_to(repo_root)
                    matches.append(str(rel).replace("\\", "/"))
                except ValueError:
                    continue

        matches.sort()
        if not matches:
            return f"No files matched pattern '{pattern}' in '{path}'"

        return f"Found {len(matches)} matching file(s):\n" + "\n".join(matches[:100])


class SearchCodeTool(BaseTool):
    """Tool to search for code / text inside files."""

    name = "search_code"
    description = "Search file contents for a string or regex pattern."
    permission_type = PermissionType.READ
    risk_level = RiskLevel.SAFE

    def get_parameter_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Text or regex pattern to search for"},
                "path": {"type": "string", "description": "Subdirectory to search in, defaults to '.'"},
                "is_regex": {"type": "boolean", "description": "Whether query is a regular expression"},
                "max_results": {"type": "integer", "description": "Maximum number of matching lines to return"},
                "repository_path": {"type": "string", "description": "Root workspace repository path"},
            },
            "required": ["query", "repository_path"],
        }

    def run(
        self,
        query: str,
        repository_path: str,
        path: str = ".",
        is_regex: bool = False,
        max_results: int = 50,
        **kwargs,
    ) -> str:
        base_dir = PathValidator.resolve_safe_path(path, repository_path)
        if not base_dir.exists():
            raise FileNotFoundError(f"Search directory not found: {path}")

        repo_root = Path(repository_path).resolve()
        compiled_regex = re.compile(query if is_regex else re.escape(query), re.IGNORECASE)

        results: List[str] = []
        for file_path in base_dir.rglob("*"):
            if not file_path.is_file() or should_ignore(file_path):
                continue

            try:
                rel_path = str(file_path.relative_to(repo_root)).replace("\\", "/")
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    for line_num, line in enumerate(f, start=1):
                        if compiled_regex.search(line):
                            results.append(f"{rel_path}:{line_num}: {line.strip()[:140]}")
                            if len(results) >= max_results:
                                break
            except Exception:
                continue

            if len(results) >= max_results:
                break

        if not results:
            return f"No matches found for query: '{query}'"

        return f"Found {len(results)} match(es):\n" + "\n".join(results)
