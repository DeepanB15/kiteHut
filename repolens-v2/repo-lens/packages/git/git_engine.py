import subprocess
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass


@dataclass
class CommitInfo:
    hash: str
    author_name: str
    author_email: str
    message: str
    date: Optional[str] = None
    changed_files: List[str] = None


class GitEngine:
    """Git analysis for change history and blast radius."""

    def __init__(self, repo_path: Path):
        self.repo_path = Path(repo_path)

    def _run(self, args) -> str:
        result = subprocess.run(
            ["git"] + args,
            cwd=str(self.repo_path),
            capture_output=True,
            text=True,
            timeout=30,
        )
        return result.stdout if result.returncode == 0 else ""

    def get_commits(self, limit: int = 10) -> List[CommitInfo]:
        raw = self._run(["log", f"--max-count={limit}", "--pretty=format:%H|%an|%ae|%ad|%s", "--date=short"])
        commits = []
        for line in raw.strip().splitlines():
            parts = line.split("|", 4)
            if len(parts) >= 5:
                commits.append(CommitInfo(
                    hash=parts[0],
                    author_name=parts[1],
                    author_email=parts[2],
                    date=parts[3],
                    message=parts[4],
                    changed_files=[],
                ))
        return commits

    def get_changed_files_for_commit(self, commit_hash: str) -> List[str]:
        raw = self._run(["diff-tree", "--no-commit-id", "--name-only", "-r", commit_hash])
        return [line for line in raw.strip().splitlines() if line]
