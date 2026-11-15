"""
Security regression tests: repository path containment for patch application
and explicit remediation approval.

Every test operates on a temporary repository; no real user files or databases
are touched.
"""

import os
from pathlib import Path
import subprocess

import pytest

from app.action.executor.patch_applier import PatchApplier
from app.action.loop.remediation_loop import ActionRemediationLoop
from app.action.models.patch import FileChangeType, FilePatch, ProposedPatch
from app.agent.memory.task_memory import TaskMemory
from app.agent.permissions.manager import PermissionManager
from app.agent.permissions.policies import DecisionType
from app.core.path_guard import PathContainmentError
from app.intelligence.models.findings import Finding, FindingCategory, FindingSeverity


@pytest.fixture
def repo(tmp_path):
    """Temporary repository root with an existing source file."""
    root = tmp_path / "repo"
    (root / "src").mkdir(parents=True)
    (root / "src" / "app.py").write_text("value = 1\n", encoding="utf-8")
    return root


@pytest.fixture
def outside(tmp_path):
    """Temporary directory that sits outside the repository root."""
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    (outside_dir / "secret.txt").write_text("do not touch\n", encoding="utf-8")
    return outside_dir


def make_patch(*file_patches: FilePatch) -> ProposedPatch:
    return ProposedPatch(
        finding_id="find_sec_001",
        title="Security regression patch",
        description="Patch used by containment and approval tests.",
        file_patches=list(file_patches),
    )


def modify(path: str, content: str = "value = 2\n") -> FilePatch:
    return FilePatch(file_path=path, change_type=FileChangeType.MODIFY, new_content=content)


def create(path: str, content: str = "created = True\n") -> FilePatch:
    return FilePatch(file_path=path, change_type=FileChangeType.CREATE, new_content=content)


def delete(path: str) -> FilePatch:
    return FilePatch(file_path=path, change_type=FileChangeType.DELETE)


def snapshot_tree(root: Path) -> dict:
    """Map every file in the repository to its bytes, for unchanged-repo assertions."""
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def make_dir_symlink(link: Path, target: Path) -> bool:
    """Create a directory symlink/junction, returning False when unsupported."""
    try:
        os.symlink(target, link, target_is_directory=True)
        return True
    except (OSError, NotImplementedError):
        pass
    if os.name == "nt":
        result = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(target)],
            capture_output=True,
            text=True,
        )
        return result.returncode == 0
    return False


# ---------------------------------------------------------------------------
# Task 1: repository path containment
# ---------------------------------------------------------------------------


def test_traversal_target_is_rejected(repo, outside):
    """'../' traversal must be rejected before any file is modified."""
    applier = PatchApplier(str(repo))

    with pytest.raises(PathContainmentError):
        applier.apply_patch(make_patch(modify("../outside/secret.txt", "owned\n")))

    assert (outside / "secret.txt").read_text(encoding="utf-8") == "do not touch\n"


def test_absolute_path_outside_repository_is_rejected(repo, outside):
    """An absolute target outside the root must be rejected."""
    applier = PatchApplier(str(repo))
    target = outside / "absolute_evil.txt"

    with pytest.raises(PathContainmentError):
        applier.apply_patch(make_patch(create(str(target))))

    assert not target.exists()


def test_absolute_path_inside_repository_is_rejected(repo):
    """Patch targets are repo-relative; absolute paths are rejected outright."""
    applier = PatchApplier(str(repo))

    with pytest.raises(PathContainmentError):
        applier.apply_patch(make_patch(modify(str(repo / "src" / "app.py"))))

    assert (repo / "src" / "app.py").read_text(encoding="utf-8") == "value = 1\n"


def test_symlink_escape_is_rejected(repo, outside):
    """A symlinked directory escaping the root must not be written through."""
    link = repo / "linked_outside"
    if not make_dir_symlink(link, outside):
        pytest.skip("Symlink creation is not permitted in this environment")

    applier = PatchApplier(str(repo))

    with pytest.raises(PathContainmentError):
        applier.apply_patch(make_patch(create("linked_outside/escaped.py")))

    assert not (outside / "escaped.py").exists()


def test_valid_nested_repository_paths_are_applied(repo):
    """Legitimate nested paths inside the repository still apply normally."""
    applier = PatchApplier(str(repo))
    task_mem = TaskMemory(task_id="nested", repository_path=str(repo))

    modified = applier.apply_patch(
        make_patch(
            modify("src/app.py"),
            create("src/pkg/deep/new_module.py", "def helper():\n    return True\n"),
            create("./src/pkg/./sibling.py", "sibling = True\n"),
        ),
        task_memory=task_mem,
    )

    assert sorted(modified) == ["src/app.py", "src/pkg/deep/new_module.py", "src/pkg/sibling.py"]
    assert (repo / "src" / "app.py").read_text(encoding="utf-8") == "value = 2\n"
    assert (repo / "src" / "pkg" / "deep" / "new_module.py").exists()
    assert (repo / "src" / "pkg" / "sibling.py").exists()


@pytest.mark.parametrize("change_type", list(FileChangeType))
def test_create_modify_delete_reject_traversal(repo, outside, change_type):
    """Containment applies equally to CREATE, MODIFY and DELETE."""
    applier = PatchApplier(str(repo))
    patch = make_patch(FilePatch(file_path="../outside/secret.txt", change_type=change_type, new_content="x\n"))

    with pytest.raises(PathContainmentError):
        applier.apply_patch(patch)

    assert (outside / "secret.txt").read_text(encoding="utf-8") == "do not touch\n"


@pytest.mark.parametrize("change_type", list(FileChangeType))
def test_create_modify_delete_reject_absolute_outside(repo, outside, change_type):
    """Containment applies equally to absolute out-of-root targets."""
    applier = PatchApplier(str(repo))
    target = outside / "abs_target.txt"
    patch = make_patch(FilePatch(file_path=str(target), change_type=change_type, new_content="x\n"))

    with pytest.raises(PathContainmentError):
        applier.apply_patch(patch)

    assert not target.exists()


def test_delete_inside_repository_still_works(repo):
    """Valid in-repo deletions are untouched by the guard."""
    obsolete = repo / "src" / "obsolete.py"
    obsolete.write_text("obsolete = True\n", encoding="utf-8")
    applier = PatchApplier(str(repo))

    modified = applier.apply_patch(make_patch(delete("src/obsolete.py")))

    assert modified == ["src/obsolete.py"]
    assert not obsolete.exists()


def test_unsafe_target_aborts_before_any_file_is_modified(repo, outside):
    """A mixed patch fails safely: the valid MODIFY must not be applied."""
    applier = PatchApplier(str(repo))
    task_mem = TaskMemory(task_id="mixed", repository_path=str(repo))

    with pytest.raises(PathContainmentError):
        applier.apply_patch(
            make_patch(
                modify("src/app.py"),
                create("../outside/evil.py"),
            ),
            task_memory=task_mem,
        )

    assert (repo / "src" / "app.py").read_text(encoding="utf-8") == "value = 1\n"
    assert not (outside / "evil.py").exists()
    assert task_mem.snapshots == {}


def test_rollback_after_failed_patch(repo):
    """A failure mid-patch rolls back earlier files and removes created files."""
    applier = PatchApplier(str(repo))
    task_mem = TaskMemory(task_id="rollback", repository_path=str(repo))
    (repo / "src" / "new_file.py").write_text("temporary = 1\n", encoding="utf-8")
    before = snapshot_tree(repo)

    # Second target is an existing directory, so writing it fails after the
    # first file was already modified.
    with pytest.raises(RuntimeError):
        applier.apply_patch(
            make_patch(
                modify("src/app.py"),
                create("src/new_file.py", "temporary = 2\n"),
                create("src"),
            ),
            task_memory=task_mem,
        )

    assert (repo / "src" / "app.py").read_text(encoding="utf-8") == "value = 1\n"
    assert snapshot_tree(repo) == before


# ---------------------------------------------------------------------------
# Task 2: explicit remediation approval
# ---------------------------------------------------------------------------


def make_finding() -> Finding:
    return Finding(
        category=FindingCategory.CONFIGURATION,
        severity=FindingSeverity.LOW,
        confidence=80.0,
        title="Missing SECURITY_TOKEN in .env.example",
        description="Token is used in code but not documented.",
        file_path="src/app.py",
    )


def stub_planner(loop: ActionRemediationLoop, monkeypatch) -> ProposedPatch:
    """Replace the planner with a deterministic in-repo patch."""
    patch = make_patch(modify("src/app.py", "value = 2\n"))
    monkeypatch.setattr(loop.planner, "plan_fix", lambda finding: patch)
    return patch


def test_default_remediation_is_denied(repo, monkeypatch):
    """Default remediation (no approval callback configured) must not modify files."""
    loop = ActionRemediationLoop(str(repo))
    stub_planner(loop, monkeypatch)
    before = snapshot_tree(repo)

    result = loop.remediate_finding(make_finding(), run_tests=False)

    assert result.success is False
    assert result.error == "Permission denied"
    assert snapshot_tree(repo) == before


def test_explicit_approval_applies_patch(repo, monkeypatch):
    """An explicit ALLOW_ONCE decision permits the remediation."""
    permission_manager = PermissionManager(
        approval_callback=lambda request: DecisionType.ALLOW_ONCE,
        auto_allow_safe=True,
    )
    loop = ActionRemediationLoop(str(repo), permission_manager=permission_manager)
    stub_planner(loop, monkeypatch)

    result = loop.remediate_finding(make_finding(), run_tests=False)

    assert result.success is True
    assert result.modified_files == ["src/app.py"]
    assert (repo / "src" / "app.py").read_text(encoding="utf-8") == "value = 2\n"


def test_approval_denial_leaves_repository_unchanged(repo, monkeypatch):
    """A DENY decision aborts with byte-for-byte unchanged repository contents."""
    permission_manager = PermissionManager(
        approval_callback=lambda request: DecisionType.DENY,
        auto_allow_safe=True,
    )
    loop = ActionRemediationLoop(str(repo), permission_manager=permission_manager)
    patch = stub_planner(loop, monkeypatch)
    before = snapshot_tree(repo)

    result = loop.remediate_finding(make_finding(), run_tests=False)

    assert result.success is False
    assert result.error == "Permission denied"
    assert result.modified_files == []
    assert result.applied_patch_id is None
    assert patch.patch_id  # planner ran, but nothing was applied
    assert snapshot_tree(repo) == before
