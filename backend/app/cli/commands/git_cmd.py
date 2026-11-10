"""
`kitehut git` subcommands.
Safe Git version control automation with conventional commit generation.
"""

from pathlib import Path
from typing import Optional
import click

from app.cli.ui import (
    bold,
    cyan,
    dim,
    green,
    print_bullet,
    print_error,
    print_header,
    print_info,
    print_success,
    print_warning,
    red,
    yellow,
)
from app.git_ops.git_manager import GitManager


@click.group(name="git")
def git_group():
    """Git version control automation, diff inspection, and conventional commits."""
    pass


@git_group.command(name="status")
@click.option(
    "--path",
    "-p",
    "repo_path",
    default=".",
    type=click.Path(exists=True, file_okay=False, dir_okay=True, readable=True),
    help="Target repository directory path.",
)
def git_status_command(repo_path: str):
    """Show detailed working tree and staging status."""
    root = Path(repo_path).resolve()
    try:
        git_mgr = GitManager(str(root))
        status = git_mgr.get_status()
    except Exception as error:
        print_error(f"Git error: {error}")
        return

    print_header(f"Git Status -- {root.name}")
    print_bullet(f"Branch:    {cyan(status.branch)}")
    print_bullet(f"Status:    {red('Dirty') if status.is_dirty else green('Clean')}")

    if status.staged_files:
        print("\n" + green(bold("Changes Staged for Commit:")))
        for f in status.staged_files:
            print(f"  {green('+')} {f}")

    if status.modified_files:
        print("\n" + yellow(bold("Changes Not Staged for Commit:")))
        for f in status.modified_files:
            print(f"  {yellow('M')} {f}")

    if status.untracked_files:
        print("\n" + red(bold("Untracked Files:")))
        for f in status.untracked_files:
            print(f"  {red('?')} {f}")

    if not status.is_dirty:
        print_success("Working tree clean, nothing to commit.")


@git_group.command(name="diff")
@click.option(
    "--path",
    "-p",
    "repo_path",
    default=".",
    type=click.Path(exists=True, file_okay=False, dir_okay=True, readable=True),
    help="Target repository directory path.",
)
@click.option(
    "--staged",
    is_flag=True,
    help="Show staged diff instead of unstaged working tree diff.",
)
def git_diff_command(repo_path: str, staged: bool):
    """Display Git diff for working tree or staging area."""
    root = Path(repo_path).resolve()
    try:
        git_mgr = GitManager(str(root))
        if staged:
            diff_text = git_mgr.repo.git.diff("--staged")
        else:
            diff_text = git_mgr.repo.git.diff()
    except Exception as error:
        print_error(f"Failed to get Git diff: {error}")
        return

    print_header(f"Git Diff ({'Staged' if staged else 'Working Tree'})")
    if not diff_text.strip():
        print_info("No diff found.")
        return

    for line in diff_text.splitlines():
        if line.startswith("+"):
            print(green(line))
        elif line.startswith("-"):
            print(red(line))
        elif line.startswith("@"):
            print(cyan(line))
        else:
            print(line)


@git_group.command(name="commit")
@click.option(
    "--path",
    "-p",
    "repo_path",
    default=".",
    type=click.Path(exists=True, file_okay=False, dir_okay=True, readable=True),
    help="Target repository directory path.",
)
@click.option(
    "--message",
    "-m",
    default=None,
    help="Explicit commit message. If omitted, generates conventional commit message.",
)
@click.option(
    "--all",
    "-a",
    "stage_all",
    is_flag=True,
    help="Automatically stage all modified and untracked files.",
)
def git_commit_command(repo_path: str, message: Optional[str], stage_all: bool):
    """Stage changes and create a Git commit with conventional commit standards."""
    root = Path(repo_path).resolve()
    try:
        git_mgr = GitManager(str(root))
        status = git_mgr.get_status()

        if not status.is_dirty:
            print_warning("No changes detected in working tree to commit.")
            return

        # Stage if requested or if nothing staged yet
        if stage_all or not status.staged_files:
            git_mgr.stage_files(["*"])
            status = git_mgr.get_status()

        # Generate message if not provided
        if not message:
            diff_text = git_mgr.repo.git.diff("HEAD") if git_mgr.repo.head.is_valid() else ""
            message = git_mgr.generate_conventional_commit_message(
                diff_text=diff_text,
                task_summary="code improvements and fixes",
            )

        print_header("Git Commit Confirmation")
        print(bold("Commit Message Preview:"))
        print(dim("----------------------------------------"))
        print(cyan(message))
        print(dim("----------------------------------------"))

        if click.confirm("Proceed with commit?", default=True):
            commit_res = git_mgr.commit(message=message)
            print_success(f"Created commit {bold(commit_res.short_hash)}: {message.splitlines()[0]}")
            print_bullet(f"Files committed: {len(commit_res.files_changed)}")
        else:
            print_info("Commit cancelled.")

    except Exception as error:
        print_error(f"Commit failed: {error}")
