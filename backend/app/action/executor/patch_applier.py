"""
Patch Applier for RepoLens Action Engine.

Safely applies FilePatch sets with automatic pre-modification snapshotting via TaskMemory.
"""

import logging
from pathlib import Path
from typing import List, Optional, Tuple

from app.action.models.patch import FileChangeType, FilePatch, ProposedPatch
from app.agent.memory.task_memory import TaskMemory
from app.core.path_guard import resolve_repository_path

logger = logging.getLogger("repolens.action.executor")


class PatchApplier:
    """Applies multi-file patches with atomic rollback snapshotting."""

    def __init__(self, repository_path: str):
        self.root = Path(repository_path).resolve()

    def _resolve_targets(
        self, patch: ProposedPatch
    ) -> List[Tuple[FilePatch, str, Path]]:
        """
        Resolve and validate every patch target before touching the filesystem.

        Raises PathContainmentError if any target is absolute, traverses with
        '..', or resolves (through symlinks) outside the repository root.
        """
        targets: List[Tuple[FilePatch, str, Path]] = []
        for file_patch in patch.file_patches:
            full_path = resolve_repository_path(self.root, file_patch.file_path)
            rel_path = full_path.relative_to(self.root).as_posix()
            targets.append((file_patch, rel_path, full_path))
        return targets

    def apply_patch(
        self,
        patch: ProposedPatch,
        task_memory: Optional[TaskMemory] = None,
    ) -> List[str]:
        """Apply all file patches in ProposedPatch. Snapshots original content before modification."""
        # Validate the entire patch up front: a single unsafe target aborts the
        # whole operation before any file is created, modified, or deleted.
        targets = self._resolve_targets(patch)

        modified_files: List[str] = []

        for file_patch, rel_path, full_path in targets:
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
