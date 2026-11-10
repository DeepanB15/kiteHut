"""
Unit Tests for Git Automation Subsystem (Layer 10).
"""

from pathlib import Path
from app.git_ops.git_manager import GitManager
from app.intelligence.models.findings import Finding, FindingCategory, FindingSeverity


def test_git_manager_status_and_branch_lifecycle(temp_git_repo):
    """Verify GitManager inspects working tree, creates branches, and switches branches."""
    ws = temp_git_repo
    git_mgr = GitManager(str(ws))

    # Initial status
    status = git_mgr.get_status()
    assert status.branch in ("master", "main")
    assert status.is_detached is False
    assert status.is_dirty is False

    # Create new file -> becomes untracked
    new_file = ws / "new_file.py"
    new_file.write_text("print('hello')\n", encoding="utf-8")

    status_dirty = git_mgr.get_status()
    assert status_dirty.is_dirty is True
    assert "new_file.py" in status_dirty.untracked_files

    # Create & switch branch
    new_branch = git_mgr.create_branch("feature/auth-remediation")
    assert new_branch == "feature/auth-remediation"
    assert git_mgr.get_status().branch == "feature/auth-remediation"

    # List branches
    branches = git_mgr.list_branches()
    assert len(branches) >= 2
    branch_names = [b.name for b in branches]
    assert "feature/auth-remediation" in branch_names


def test_git_manager_stage_commit_and_history(temp_git_repo):
    """Verify GitManager stages changes, generates conventional commit, and commits."""
    ws = temp_git_repo
    git_mgr = GitManager(str(ws))

    # Create file and stage
    doc_file = ws / "README_UPDATE.md"
    doc_file.write_text("# Updated Documentation\n", encoding="utf-8")

    staged = git_mgr.stage_files(["README_UPDATE.md"])
    assert "README_UPDATE.md" in staged

    # Conventional commit generation
    finding = Finding(
        category=FindingCategory.SECURITY,
        severity=FindingSeverity.HIGH,
        confidence=95.0,
        title="Hardcoded API Secret in config",
        description="Replaced plaintext key with os.getenv",
        file_path="src/config.py",
    )
    conv_msg = git_mgr.generate_conventional_commit_message(
        diff_text="diff --git a/src/config.py",
        findings_resolved=[finding],
    )
    assert "fix(security): resolve hardcoded api secret in config" in conv_msg
    assert "Co-Authored-By: RepoLens Agent" in conv_msg

    # Commit
    commit = git_mgr.commit(conv_msg)
    assert commit.commit_hash is not None
    assert len(commit.short_hash) == 7
    assert "README_UPDATE.md" in commit.files_changed

    # History
    history = git_mgr.get_history(max_count=5)
    assert len(history) >= 1
    assert history[0].commit_hash == commit.commit_hash
