"""
Git Version Control Tools for RepoLens Agent.

Includes:
- git_status (SAFE)
- git_diff (SAFE)
- git_log (SAFE)
- git_branch (SAFE)
- git_commit (APPROVAL_REQUIRED)
- git_checkout (APPROVAL_REQUIRED)
"""

from pathlib import Path
from typing import Any, Dict, List, Optional
from git import Repo, GitCommandError

from app.agent.permissions.policies import PermissionType, RiskLevel
from app.tools.base import BaseTool
from app.tools.sandbox import PathValidator


class GitStatusTool(BaseTool):
    """Tool to inspect Git working tree status."""

    name = "git_status"
    description = "Check git status (modified, untracked, staged files)."
    permission_type = PermissionType.GIT
    risk_level = RiskLevel.SAFE

    def get_parameter_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "repository_path": {"type": "string", "description": "Root workspace repository path"},
            },
            "required": ["repository_path"],
        }

    def run(self, repository_path: str, **kwargs) -> str:
        repo_root = Path(repository_path).resolve()
        try:
            repo = Repo(repo_root)
        except Exception as error:
            raise RuntimeError(f"Failed to open git repository at {repo_root}: {error}")

        status_text = repo.git.status(porcelain=False)
        branch = repo.active_branch.name if not repo.head.is_detached else "DETACHED_HEAD"

        return f"=== Git Status (Branch: {branch}) ===\n{status_text}"


class GitDiffTool(BaseTool):
    """Tool to view git diffs."""

    name = "git_diff"
    description = "View git diff for working tree or specific files."
    permission_type = PermissionType.GIT
    risk_level = RiskLevel.SAFE

    def get_parameter_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Optional specific file to diff"},
                "staged": {"type": "boolean", "description": "Whether to view staged changes (--cached)"},
                "repository_path": {"type": "string", "description": "Root workspace repository path"},
            },
            "required": ["repository_path"],
        }

    def run(
        self,
        repository_path: str,
        file_path: Optional[str] = None,
        staged: bool = False,
        **kwargs,
    ) -> str:
        repo_root = Path(repository_path).resolve()
        repo = Repo(repo_root)

        args = []
        if staged:
            args.append("--cached")
        if file_path:
            args.extend(["--", file_path])

        diff_text = repo.git.diff(*args)
        if not diff_text.strip():
            return "No changes detected in git diff."

        return diff_text


class GitLogTool(BaseTool):
    """Tool to view recent git commits."""

    name = "git_log"
    description = "View recent git commit history."
    permission_type = PermissionType.GIT
    risk_level = RiskLevel.SAFE

    def get_parameter_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "max_count": {"type": "integer", "description": "Number of commits to retrieve (default: 10)"},
                "repository_path": {"type": "string", "description": "Root workspace repository path"},
            },
            "required": ["repository_path"],
        }

    def run(
        self,
        repository_path: str,
        max_count: int = 10,
        **kwargs,
    ) -> str:
        repo_root = Path(repository_path).resolve()
        repo = Repo(repo_root)

        log_output = repo.git.log(f"-{max_count}", "--oneline", "--decorate")
        return f"=== Recent Commits (Top {max_count}) ===\n{log_output}"


class GitBranchTool(BaseTool):
    """Tool to inspect git branches."""

    name = "git_branch"
    description = "List local git branches and show the active branch."
    permission_type = PermissionType.GIT
    risk_level = RiskLevel.SAFE

    def get_parameter_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "repository_path": {"type": "string", "description": "Root workspace repository path"},
            },
            "required": ["repository_path"],
        }

    def run(self, repository_path: str, **kwargs) -> str:
        repo_root = Path(repository_path).resolve()
        repo = Repo(repo_root)

        branches = repo.git.branch("-a")
        return f"=== Git Branches ===\n{branches}"


class GitCommitTool(BaseTool):
    """Tool to stage and commit changes."""

    name = "git_commit"
    description = "Stage files and create a git commit with a message."
    permission_type = PermissionType.GIT
    risk_level = RiskLevel.APPROVAL_REQUIRED

    def get_parameter_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "Commit message"},
                "files": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional list of files to stage (defaults to all modified files)",
                },
                "repository_path": {"type": "string", "description": "Root workspace repository path"},
            },
            "required": ["message", "repository_path"],
        }

    def run(
        self,
        message: str,
        repository_path: str,
        files: Optional[List[str]] = None,
        **kwargs,
    ) -> str:
        if not message.strip():
            raise ValueError("Commit message cannot be empty.")

        repo_root = Path(repository_path).resolve()
        repo = Repo(repo_root)

        if files:
            for f in files:
                repo.git.add(f)
        else:
            repo.git.add("-A")

        commit_res = repo.git.commit("-m", message)
        return f"=== Git Commit Created ===\n{commit_res}"


class GitCheckoutTool(BaseTool):
    """Tool to checkout branches or files."""

    name = "git_checkout"
    description = "Switch branch or restore files from git."
    permission_type = PermissionType.GIT
    risk_level = RiskLevel.APPROVAL_REQUIRED

    def get_parameter_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "target": {"type": "string", "description": "Branch name or file path to checkout"},
                "create_branch": {"type": "boolean", "description": "Create and switch to a new branch (-b)"},
                "repository_path": {"type": "string", "description": "Root workspace repository path"},
            },
            "required": ["target", "repository_path"],
        }

    def run(
        self,
        target: str,
        repository_path: str,
        create_branch: bool = False,
        **kwargs,
    ) -> str:
        repo_root = Path(repository_path).resolve()
        repo = Repo(repo_root)

        if create_branch:
            res = repo.git.checkout("-b", target)
        else:
            res = repo.git.checkout(target)

        return f"=== Git Checkout ===\nSwitched to / Checked out: {target}\n{res}"
