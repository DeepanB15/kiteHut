"""
Unit Tests for Action Engine: FixPlanner, PatchApplier, and TestRunner (Layer 8).
"""

from pathlib import Path
from app.action.executor.patch_applier import PatchApplier
from app.action.models.patch import FileChangeType, FilePatch, ProposedPatch
from app.action.planner.fix_planner import FixPlanner
from app.action.verifier.test_runner import TestRunner
from app.agent.memory.task_memory import TaskMemory
from app.intelligence.models.findings import Finding, FindingCategory, FindingSeverity


def test_fix_planner_config_recipe(temp_workspace):
    """Verify fix planner creates patch for missing env variable."""
    ws = temp_workspace
    planner = FixPlanner(str(ws))

    finding = Finding(
        category=FindingCategory.CONFIGURATION,
        severity=FindingSeverity.MEDIUM,
        confidence=85.0,
        title="Missing DATABASE_URL in .env.example",
        description="DATABASE_URL is used in code but not documented in .env.example",
        file_path="src/db.py",
    )

    patch = planner.plan_fix(finding)
    assert len(patch.file_patches) >= 1
    env_patch = patch.file_patches[0]
    assert env_patch.file_path == ".env.example"
    assert "DATABASE_URL=" in env_patch.new_content


def test_fix_planner_secret_recipe(temp_workspace):
    """Verify fix planner creates patch for plaintext secret."""
    ws = temp_workspace
    vuln_file = ws / "src" / "api.py"
    vuln_file.write_text("api_key = 'sk_live_999988887777'\n", encoding="utf-8")

    planner = FixPlanner(str(ws))
    finding = Finding(
        category=FindingCategory.SECURITY,
        severity=FindingSeverity.HIGH,
        confidence=90.0,
        title="Hardcoded API Secret Detected",
        description="Plaintext Stripe token found in source code.",
        file_path="src/api.py",
    )

    patch = planner.plan_fix(finding)
    assert len(patch.file_patches) == 2
    paths = {p.file_path for p in patch.file_patches}
    assert "src/api.py" in paths
    assert ".env.example" in paths

    src_patch = next(p for p in patch.file_patches if p.file_path == "src/api.py")
    assert "os.getenv(" in src_patch.new_content


def test_fix_planner_dependency_recipe(temp_workspace):
    """Verify fix planner creates patch for unpinned dependencies."""
    ws = temp_workspace
    req = ws / "requirements.txt"
    req.write_text("fastapi>=0.100.0\nuvicorn>=0.22.0\n", encoding="utf-8")

    planner = FixPlanner(str(ws))
    finding = Finding(
        category=FindingCategory.DEPENDENCY,
        severity=FindingSeverity.LOW,
        confidence=80.0,
        title="Unpinned dependencies in requirements.txt",
        description="Dependencies use >= instead of pinned versions.",
        file_path="requirements.txt",
    )

    patch = planner.plan_fix(finding)
    assert len(patch.file_patches) == 1
    assert "fastapi==0.100.0" in patch.file_patches[0].new_content


def test_fix_planner_debug_cleanup_recipe(temp_workspace):
    """Verify fix planner strips debug print and breakpoint calls."""
    ws = temp_workspace
    src = ws / "src" / "worker.py"
    src.write_text(
        "def work():\n    print('debugging worker')\n    breakpoint()\n    return 42\n",
        encoding="utf-8",
    )

    planner = FixPlanner(str(ws))
    finding = Finding(
        category=FindingCategory.CODE_REVIEW,
        severity=FindingSeverity.LOW,
        confidence=80.0,
        title="Leftover Debug Statements",
        description="print and breakpoint statements present in worker.py.",
        file_path="src/worker.py",
    )

    patch = planner.plan_fix(finding)
    assert len(patch.file_patches) == 1
    new_content = patch.file_patches[0].new_content
    assert "print(" not in new_content
    assert "breakpoint()" not in new_content
    assert "return 42" in new_content


def test_patch_applier_and_snapshot_rollback(temp_workspace):
    """Verify PatchApplier writes modifications and cleanly rolls back on demand."""
    ws = temp_workspace
    target_file = ws / "src" / "target.py"
    target_file.write_text("initial_value = 100\n", encoding="utf-8")

    applier = PatchApplier(str(ws))
    task_mem = TaskMemory(task_id="test_patch_task", repository_path=str(ws))

    # Create patch
    patch = ProposedPatch(
        finding_id="find_001",
        title="Update target value",
        description="Changes initial_value to 200",
        file_patches=[
            FilePatch(
                file_path="src/target.py",
                change_type=FileChangeType.MODIFY,
                original_content="initial_value = 100\n",
                new_content="initial_value = 200\n",
                description="Update to 200",
            ),
            FilePatch(
                file_path="src/new_helper.py",
                change_type=FileChangeType.CREATE,
                original_content="",
                new_content="def helper(): return True\n",
                description="Create helper",
            ),
        ],
    )

    # Apply
    modified = applier.apply_patch(patch, task_memory=task_mem)
    assert len(modified) == 2
    assert target_file.read_text(encoding="utf-8") == "initial_value = 200\n"
    assert (ws / "src" / "new_helper.py").exists()

    # Rollback via TaskMemory
    task_mem.rollback_all()
    assert target_file.read_text(encoding="utf-8") == "initial_value = 100\n"
    assert not (ws / "src" / "new_helper.py").exists()
