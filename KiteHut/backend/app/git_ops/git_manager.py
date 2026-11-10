"""
Git Automation Manager for RepoLens (Layer 10).
"""

from datetime import datetime, timezone
import logging
from pathlib import Path
import re
from typing import List, Optional
from git import Actor, GitCommandError, Repo

from app.git_ops.models.git_models import BranchInfo, GitCommit, GitStatus
from app.intelligence.models.findings import Finding

logger = logging.getLogger("repolens.git_ops")


class GitManager:
    """Manages Git version control operations with safety checks and structured telemetry."""

    def __init__(self, repository_path: str):
        self.root = Path(repository_path).resolve()
        try:
            self.repo = Repo(self.root, search_parent_directories=True)
        except Exception as error:
            logger.error("Failed to initialize Git repository at %s: %s", self.root, error)
            raise RuntimeError(f"Directory is not a valid Git repository: {self.root}") from error

    def get_status(self) -> GitStatus:
        """Inspect and return structured repository working tree status."""
        is_detached = self.repo.head.is_detached
        branch = "DETACHED_HEAD" if is_detached else self.repo.active_branch.name

        # Staged diff
        staged_files = [item.a_path for item in self.repo.index.diff("HEAD")] if not is_detached and self.repo.head.is_valid() else []

        # Unstaged modified & deleted
        modified_files = []
        deleted_files = []
        for item in self.repo.index.diff(None):
            if item.deleted_file:
                deleted_files.append(item.a_path)
            else:
                modified_files.append(item.a_path)

        # Untracked
        untracked_files = list(self.repo.untracked_files)

        # Ahead / Behind
        ahead = 0
        behind = 0
        if not is_detached:
            try:
                tracking = self.repo.active_branch.tracking_branch()
                if tracking:
                    ahead = len(list(self.repo.iter_commits(f"{tracking.name}..{branch}")))
                    behind = len(list(self.repo.iter_commits(f"{branch}..{tracking.name}")))
            except Exception:
                pass

        is_dirty = bool(staged_files or modified_files or deleted_files or untracked_files)

        return GitStatus(
            branch=branch,
            is_detached=is_detached,
            is_dirty=is_dirty,
            staged_files=staged_files,
            modified_files=modified_files,
            untracked_files=untracked_files,
            deleted_files=deleted_files,
            ahead_count=ahead,
            behind_count=behind,
        )

    def get_diff(self, file_path: Optional[str] = None, staged: bool = False) -> str:
        """Generate unified git diff for working tree or staged changes."""
        try:
            if staged:
                if file_path:
                    return self.repo.git.diff("--cached", "--", file_path)
                return self.repo.git.diff("--cached")
            else:
                if file_path:
                    return self.repo.git.diff("--", file_path)
                return self.repo.git.diff()
        except GitCommandError as error:
            logger.error("Git diff failed: %s", error)
            return ""

    def list_branches(self) -> List[BranchInfo]:
        """List local repository branches."""
        current_name = None if self.repo.head.is_detached else self.repo.active_branch.name
        branches = []
        for head in self.repo.heads:
            tracking = head.tracking_branch()
            branches.append(
                BranchInfo(
                    name=head.name,
                    is_current=(head.name == current_name),
                    commit_hash=head.commit.hexsha,
                    tracking_remote=tracking.name if tracking else None,
                )
            )
        return branches

    def create_branch(self, branch_name: str, start_point: Optional[str] = None) -> str:
        """Create and switch to a new branch."""
        # Sanitize branch name
        sanitized = re.sub(r"[^a-zA-Z0-9_\-\./]", "-", branch_name).strip("-")
        if not sanitized:
            raise ValueError("Invalid branch name")

        if start_point:
            new_head = self.repo.create_head(sanitized, commit=start_point)
        else:
            new_head = self.repo.create_head(sanitized)
        new_head.checkout()
        logger.info("Created and checked out branch: %s", sanitized)
        return sanitized

    def switch_branch(self, branch_name: str) -> str:
        """Switch to an existing branch."""
        if branch_name not in self.repo.heads:
            raise ValueError(f"Branch '{branch_name}' does not exist.")
        self.repo.heads[branch_name].checkout()
        logger.info("Switched to branch: %s", branch_name)
        return branch_name

    def stage_files(self, files: Optional[List[str]] = None) -> List[str]:
        """Stage files in index."""
        if not files or "." in files or "all" in files:
            self.repo.git.add(A=True)
            return ["*"]
        else:
            self.repo.git.add("--", *files)
            return files

    def commit(
        self,
        message: str,
        author_name: str = "RepoLens Agent",
        author_email: str = "agent@repolens.local",
    ) -> GitCommit:
        """Create a commit from currently staged changes."""
        clean_msg = message.strip()
        if not clean_msg:
            raise ValueError("Commit message cannot be empty")

        actor = Actor(author_name, author_email)
        commit_obj = self.repo.index.commit(
            clean_msg,
            author=actor,
            committer=actor,
        )

        files_changed = list(commit_obj.stats.files.keys()) if commit_obj.stats else []

        logger.info("Created commit %s: %s", commit_obj.hexsha[:7], clean_msg.splitlines()[0])
        return GitCommit(
            commit_hash=commit_obj.hexsha,
            short_hash=commit_obj.hexsha[:7],
            author_name=author_name,
            author_email=author_email,
            timestamp=datetime.fromtimestamp(commit_obj.committed_date, tz=timezone.utc),
            message=clean_msg,
            files_changed=files_changed,
        )

    def generate_conventional_commit_message(
        self,
        diff_text: str,
        findings_resolved: Optional[List[Finding]] = None,
        task_summary: Optional[str] = None,
    ) -> str:
        """Generate a structured conventional commit message based on diff and resolved findings."""
        if findings_resolved and len(findings_resolved) > 0:
            top_finding = findings_resolved[0]
            cat_map = {
                "security": "fix(security)",
                "configuration": "fix(config)",
                "testing": "test",
                "dependency": "build(deps)",
                "quality": "refactor",
                "architecture": "refactor(arch)",
                "code_review": "style",
                "api": "feat(api)",
            }
            prefix = cat_map.get(top_finding.category.value if hasattr(top_finding.category, "value") else str(top_finding.category), "fix")
            title = f"{prefix}: resolve {top_finding.title.lower()}"
            body_lines = [f"- Remediated finding {top_finding.finding_id}: {top_finding.description}"]
            for extra in findings_resolved[1:]:
                body_lines.append(f"- Remediated finding {extra.finding_id}: {extra.title}")
            body_lines.append("\nCo-Authored-By: RepoLens Agent <agent@repolens.local>")
            return f"{title}\n\n" + "\n".join(body_lines)

        if task_summary:
            return f"feat: {task_summary}\n\nAutomated commit by RepoLens Agent.\n\nCo-Authored-By: RepoLens Agent <agent@repolens.local>"

        # Generic heuristics based on diff
        if ".env" in diff_text:
            return "fix(config): update environment templates\n\nCo-Authored-By: RepoLens Agent <agent@repolens.local>"
        if "requirements.txt" in diff_text or "package.json" in diff_text:
            return "build(deps): update dependencies\n\nCo-Authored-By: RepoLens Agent <agent@repolens.local>"
        if "test" in diff_text.lower():
            return "test: update unit and integration test suites\n\nCo-Authored-By: RepoLens Agent <agent@repolens.local>"

        return "chore: update repository code [RepoLens]\n\nCo-Authored-By: RepoLens Agent <agent@repolens.local>"

    def get_history(self, max_count: int = 20) -> List[GitCommit]:
        """Fetch recent commit history."""
        commits = []
        try:
            for c in self.repo.iter_commits(max_count=max_count):
                commits.append(
                    GitCommit(
                        commit_hash=c.hexsha,
                        short_hash=c.hexsha[:7],
                        author_name=c.author.name or "Unknown",
                        author_email=c.author.email or "unknown@local",
                        timestamp=datetime.fromtimestamp(c.committed_date, tz=timezone.utc),
                        message=c.message.strip(),
                        files_changed=list(c.stats.files.keys()) if c.stats else [],
                    )
                )
        except Exception as error:
            logger.warning("Could not read commit history: %s", error)
        return commits

    def push(self, remote_name: str = "origin", branch: Optional[str] = None) -> bool:
        """Push branch to remote with safety checks."""
        target_branch = branch or (self.repo.active_branch.name if not self.repo.head.is_detached else "main")
        try:
            remote = self.repo.remote(name=remote_name)
            remote.push(refspec=f"{target_branch}:{target_branch}")
            logger.info("Pushed branch %s to remote %s", target_branch, remote_name)
            return True
        except Exception as error:
            logger.error("Git push failed: %s", error)
            return False
