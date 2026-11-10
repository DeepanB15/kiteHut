"""
Incremental Change Detector for RepoLens.

Detects filesystem modifications and Git workspace status changes.
"""

from pathlib import Path
import time
from typing import Dict, List, Optional, Set

from app.context.git.git_context import GitContextExtractor, GitWorkspaceContext
from app.monitoring.models.change_event import ChangeEvent, ChangeSource, ChangeType


class ChangeDetector:
    """Detects modified, created, and deleted files across the repository."""

    IGNORE_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build", ".pytest_cache"}

    def __init__(self, repository_path: str):
        self.root = Path(repository_path).resolve()
        self._file_mtimes: Dict[str, float] = {}
        self._initialize_snapshot()

    def _initialize_snapshot(self) -> None:
        """Record initial modification timestamps of all tracked files."""
        for path in self.root.rglob("*"):
            if path.is_file() and not self._is_ignored(path):
                rel = str(path.relative_to(self.root)).replace("\\", "/")
                try:
                    self._file_mtimes[rel] = path.stat().st_mtime
                except OSError:
                    pass

    def detect_changes(self, git_context: Optional[GitWorkspaceContext] = None) -> List[ChangeEvent]:
        """Scan workspace for changes since last check or using Git diff."""
        events: List[ChangeEvent] = []
        current_files: Set[str] = set()

        # 1. Filesystem scan
        for path in self.root.rglob("*"):
            if path.is_file() and not self._is_ignored(path):
                rel = str(path.relative_to(self.root)).replace("\\", "/")
                current_files.add(rel)
                try:
                    mtime = path.stat().st_mtime
                    if rel not in self._file_mtimes:
                        # New file created
                        events.append(
                            ChangeEvent(
                                source=self._determine_source(rel),
                                file_path=rel,
                                change_type=ChangeType.CREATED,
                            )
                        )
                    elif mtime > self._file_mtimes[rel]:
                        # Existing file modified
                        events.append(
                            ChangeEvent(
                                source=self._determine_source(rel),
                                file_path=rel,
                                change_type=ChangeType.MODIFIED,
                            )
                        )
                    self._file_mtimes[rel] = mtime
                except OSError:
                    pass

        # Check for deleted files
        deleted_files = set(self._file_mtimes.keys()) - current_files
        for rel in deleted_files:
            events.append(
                ChangeEvent(
                    source=self._determine_source(rel),
                    file_path=rel,
                    change_type=ChangeType.DELETED,
                )
            )
            del self._file_mtimes[rel]

        # 2. Enrich with Git diff if available
        if git_context and git_context.is_git_repo:
            for chg in git_context.changed_files:
                # Find matching event or add Git event
                diff_text = "\n".join(["\n".join(h.lines) for h in chg.hunks])
                matched = next((e for e in events if e.file_path == chg.file_path), None)
                if matched:
                    matched.source = ChangeSource.GIT
                    matched.diff_content = diff_text
                else:
                    events.append(
                        ChangeEvent(
                            source=ChangeSource.GIT,
                            file_path=chg.file_path,
                            change_type=ChangeType.MODIFIED if chg.status == "modified" else ChangeType.CREATED,
                            diff_content=diff_text,
                        )
                    )

        return events

    def _determine_source(self, relative_path: str) -> ChangeSource:
        """Classify change source based on file type / name."""
        lower = relative_path.lower()
        if lower.endswith((".env", ".env.example", ".env.local", "dockerfile", "docker-compose.yml")):
            return ChangeSource.CONFIGURATION
        if lower.endswith(("requirements.txt", "package.json", "cargo.toml", "pyproject.toml", "pom.xml")):
            return ChangeSource.DEPENDENCY
        return ChangeSource.FILESYSTEM

    def _is_ignored(self, path: Path) -> bool:
        """Check if path is inside an ignored directory."""
        parts = set(path.parts)
        return bool(parts & self.IGNORE_DIRS)
