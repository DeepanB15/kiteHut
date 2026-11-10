"""
Task Memory and Workspace Rollback Support for RepoLens Agent.

Maintains file modifications, rollback snapshots, and episodic memory notes
during a task's lifecycle.
"""

from datetime import datetime, timezone
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("repolens.agent.memory")


class TaskMemory:
    """
    Episodic memory tracking file snapshots, modifications, and execution notes for a single task.
    """

    def __init__(self, task_id: str, repository_path: str):
        self.task_id = task_id
        self.repository_path = Path(repository_path).resolve()
        self.snapshots: Dict[str, Optional[str]] = {}  # relative_path -> original_content (or None if newly created)
        self.notes: List[Dict[str, Any]] = []
        self.active_context_files: List[str] = []

    def record_file_snapshot(self, relative_path: str) -> None:
        """
        Record the original content of a file before modification for rollback capability.
        If the file does not exist, records None so it can be unlinked on rollback.
        """
        if relative_path in self.snapshots:
            return  # Already snapshotted initial state

        target = (self.repository_path / relative_path).resolve()
        if target.exists() and target.is_file():
            try:
                with open(target, "r", encoding="utf-8", errors="replace") as f:
                    self.snapshots[relative_path] = f.read()
                logger.debug("Captured rollback snapshot for: %s", relative_path)
            except Exception as error:
                logger.warning("Could not snapshot %s: %s", relative_path, error)
        else:
            # File did not exist initially
            self.snapshots[relative_path] = None

    def rollback_all(self) -> List[str]:
        """
        Restore all modified files to their snapshotted initial state.
        Returns list of restored file paths.
        """
        restored = []
        for rel_path, original_content in self.snapshots.items():
            target = (self.repository_path / rel_path).resolve()
            try:
                if original_content is None:
                    # Was newly created during task, delete it
                    if target.exists():
                        target.unlink()
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with open(target, "w", encoding="utf-8") as f:
                        f.write(original_content)
                restored.append(rel_path)
                logger.info("Rolled back file: %s", rel_path)
            except Exception as error:
                logger.error("Failed to rollback %s: %s", rel_path, error)
        return restored

    def rollback_file(self, relative_path: str) -> bool:
        """Restore a single file to its initial state."""
        if relative_path not in self.snapshots:
            return False

        target = (self.repository_path / relative_path).resolve()
        try:
            original_content = self.snapshots[relative_path]
            if original_content is None:
                if target.exists():
                    target.unlink()
            else:
                with open(target, "w", encoding="utf-8") as f:
                    f.write(original_content)
            return True
        except Exception as error:
            logger.error("Failed to rollback %s: %s", relative_path, error)
            return False

    def add_note(self, step_id: int, note: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        """Record an episodic observation or note."""
        self.notes.append({
            "step_id": step_id,
            "note": note,
            "metadata": metadata or {},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    def get_modified_files(self) -> List[str]:
        """Return list of all files that have recorded snapshots."""
        return list(self.snapshots.keys())
