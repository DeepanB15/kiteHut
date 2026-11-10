"""
Patch Applier for RepoLens Action Engine.

Safely applies FilePatch sets with automatic pre-modification snapshotting via TaskMemory.
"""

import logging
from pathlib import Path
from typing import List, Optional

from app.action.models.patch import FileChangeType, ProposedPatch
from app.agent.memory.task_memory import TaskMemory

logger = logging.getLogger("repolens.action.executor")


class PatchApplier:
    """Applies multi-file patches with atomic rollback snapshotting."""

    def __init__(self, repository_path: str):
        self.root = Path(repository_path).resolve()

    def apply_patch(
        self,
        patch: ProposedPatch,
        task_memory: Optional[TaskMemory] = None,
    ) -> List[str]:
        """Apply all file patches in ProposedPatch. Snapshots original content before modification."""
        modified_files: List[str] = []

        for file_patch in patch.file_patches:
            rel_path = file_patch.file_path.replace("\\", "/")
            full_path = (self.root / rel_path).resolve()

            # Record snapshot for rollback support
            if task_memory:
                task_memory.record_file_snapshot(rel_path)

            try:
                if file_patch.change_type == FileChangeType.DELETE:
                    if full_path.exists():
                        full_path.unlink()
                        modified_files.append(rel_path)
                else:
                    # CREATE or MODIFY
                    full_path.parent.mkdir(parents=True, exist_ok=True)
                    content = file_patch.new_content or ""
                    full_path.write_text(content, encoding="utf-8")
                    modified_files.append(rel_path)

                logger.info("Successfully applied patch to %s (%s)", rel_path, file_patch.change_type.value)
            except Exception as error:
                logger.error("Failed to apply patch to %s: %s", rel_path, error)
                # Attempt rollback if task memory available
                if task_memory:
                    task_memory.rollback_all()
                raise RuntimeError(f"Patch application failed on {rel_path}: {error}") from error

        return modified_files
