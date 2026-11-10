"""
Git Context Extractor for RepoLens Context Engine.

Extracts working tree status, staged/unstaged diffs, changed files, line hunks,
and recent commit history to support focused incremental agent analysis.
"""

from pathlib import Path
import re
from typing import Dict, List, Optional
from git import InvalidGitRepositoryError, NoSuchPathError, Repo
from pydantic import BaseModel, Field


class GitDiffHunk(BaseModel):
    old_start: int
    old_lines: int
    new_start: int
    new_lines: int
    lines: List[str] = Field(default_factory=list)


class ChangedFile(BaseModel):
    file_path: str
    status: str  # modified, added, deleted, renamed, untracked
    staged: bool = False
    insertions: int = 0
    deletions: int = 0
    hunks: List[GitDiffHunk] = Field(default_factory=list)
    diff_text: str = ""


class GitWorkspaceContext(BaseModel):
    is_git_repo: bool = False
    active_branch: str = "main"
    head_commit_hash: Optional[str] = None
    head_commit_message: Optional[str] = None
    is_dirty: bool = False
    untracked_files: List[str] = Field(default_factory=list)
    changed_files: List[ChangedFile] = Field(default_factory=list)
    recent_commits: List[Dict[str, str]] = Field(default_factory=list)


class GitContextExtractor:
    """Extracts git context from repository for incremental analysis."""

    def __init__(self, root_path: str):
        self.root_path = Path(root_path).resolve()

    def extract(self) -> GitWorkspaceContext:
        """Extract complete workspace git context."""
        try:
            repo = Repo(self.root_path, search_parent_directories=True)
        except (InvalidGitRepositoryError, NoSuchPathError):
            return GitWorkspaceContext(is_git_repo=False)

        try:
            active_branch = repo.active_branch.name
        except TypeError:
            active_branch = "HEAD (detached)"
        except Exception:
            active_branch = "main"

        head_commit_hash = None
        head_commit_message = None
        recent_commits: List[Dict[str, str]] = []

        try:
            if repo.head.is_valid():
                head = repo.head.commit
                head_commit_hash = head.hexsha[:8]
                head_commit_message = head.message.strip()

                for c in list(repo.iter_commits(max_count=10)):
                    recent_commits.append({
                        "hash": c.hexsha[:8],
                        "author": str(c.author),
                        "date": c.committed_datetime.isoformat(),
                        "message": c.message.strip().splitlines()[0] if c.message else "",
                    })
        except Exception:
            pass

        untracked = [str(p).replace("\\", "/") for p in repo.untracked_files]
        changed_files: List[ChangedFile] = []

        # 1. Unstaged diff
        try:
            unstaged_diff = repo.index.diff(None, create_patch=True)
            for d in unstaged_diff:
                fpath = d.b_path or d.a_path
                diff_text = d.diff.decode("utf-8", errors="ignore") if isinstance(d.diff, bytes) else str(d.diff or "")
                hunks, ins, dels = self._parse_diff_hunks(diff_text)
                changed_files.append(
                    ChangedFile(
                        file_path=str(fpath).replace("\\", "/"),
                        status="deleted" if d.deleted_file else ("added" if d.new_file else "modified"),
                        staged=False,
                        insertions=ins,
                        deletions=dels,
                        hunks=hunks,
                        diff_text=diff_text,
                    )
                )
        except Exception:
            pass

        # 2. Staged diff (index vs HEAD)
        try:
            if repo.head.is_valid():
                staged_diff = repo.head.commit.diff(create_patch=True)
                for d in staged_diff:
                    fpath = d.b_path or d.a_path
                    diff_text = d.diff.decode("utf-8", errors="ignore") if isinstance(d.diff, bytes) else str(d.diff or "")
                    hunks, ins, dels = self._parse_diff_hunks(diff_text)
                    changed_files.append(
                        ChangedFile(
                            file_path=str(fpath).replace("\\", "/"),
                            status="deleted" if d.deleted_file else ("added" if d.new_file else "modified"),
                            staged=True,
                            insertions=ins,
                            deletions=dels,
                            hunks=hunks,
                            diff_text=diff_text,
                        )
                    )
        except Exception:
            pass

        # 3. Add untracked files as 'untracked'
        for ufile in untracked:
            changed_files.append(
                ChangedFile(
                    file_path=ufile,
                    status="untracked",
                    staged=False,
                )
            )

        return GitWorkspaceContext(
            is_git_repo=True,
            active_branch=active_branch,
            head_commit_hash=head_commit_hash,
            head_commit_message=head_commit_message,
            is_dirty=repo.is_dirty(untracked_files=True),
            untracked_files=untracked,
            changed_files=changed_files,
            recent_commits=recent_commits,
        )

    def _parse_diff_hunks(self, patch: str) -> tuple[List[GitDiffHunk], int, int]:
        """Parse unified diff patch into line hunks and insertion/deletion counts."""
        hunks: List[GitDiffHunk] = []
        insertions = 0
        deletions = 0

        hunk_header_re = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
        current_hunk: Optional[GitDiffHunk] = None

        for line in patch.splitlines():
            m = hunk_header_re.match(line)
            if m:
                if current_hunk:
                    hunks.append(current_hunk)
                old_start = int(m.group(1))
                old_lines = int(m.group(2) or 1)
                new_start = int(m.group(3))
                new_lines = int(m.group(4) or 1)
                current_hunk = GitDiffHunk(
                    old_start=old_start,
                    old_lines=old_lines,
                    new_start=new_start,
                    new_lines=new_lines,
                    lines=[],
                )
            elif current_hunk:
                current_hunk.lines.append(line)
                if line.startswith("+") and not line.startswith("+++"):
                    insertions += 1
                elif line.startswith("-") and not line.startswith("---"):
                    deletions += 1

        if current_hunk:
            hunks.append(current_hunk)

        return hunks, insertions, deletions
