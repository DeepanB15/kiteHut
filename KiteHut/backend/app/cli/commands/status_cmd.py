"""
`kitehut status` command.
Displays repository status, technology stack, health score, Git state, and active findings.
"""

from pathlib import Path
import click

from app.cli.ui import (
    bold,
    cyan,
    dim,
    format_health_score,
    green,
    print_bullet,
    print_error,
    print_header,
    print_info,
    print_table,
    print_warning,
    red,
    yellow,
)
from app.context.git.git_context import GitContextExtractor
from app.context.project_map.project_map import ProjectMapBuilder
from app.intelligence.orchestrator.orchestrator import IntelligenceOrchestrator
from app.llm.factory import create_llm_provider
from app.verification.verification_engine import VerificationEngine


@click.command(name="status")
@click.option(
    "--path",
    "-p",
    "repo_path",
    default=".",
    type=click.Path(exists=True, file_okay=False, dir_okay=True, readable=True),
    help="Target repository directory path.",
)
def status_command(repo_path: str):
    """Display comprehensive repository status, health score, Git state, and findings."""
    root = Path(repo_path).resolve()
    print_header(f"KiteHut Status -- {root.name}")

    # 1. Project Context
    try:
        builder = ProjectMapBuilder(str(root))
        project_map, symbol_index, _ = builder.build()
    except Exception as error:
        print_error(f"Failed to load repository map: {error}")
        return

    # 2. Git Context
    git_extractor = GitContextExtractor(str(root))
    git_context = git_extractor.extract()

    # 3. LLM Status
    llm_status_str = dim("Not connected")
    try:
        llm = create_llm_provider()
        if hasattr(llm, "is_available") and llm.is_available():
            llm_status_str = green(f"Online ({getattr(llm, 'model', 'ollama')})")
        else:
            llm_status_str = yellow("Offline (Ollama unreachable)")
    except Exception:
        llm_status_str = yellow("Local LLM not configured")

    # Print System Information
    langs = list(project_map.structure.languages.keys()) if project_map.structure.languages else ["Unknown"]
    fw = [t.name for t in project_map.technologies] if project_map.technologies else ["None detected"]
    print(bold("Repository Context:"))
    print_bullet(f"Directory:    {root}")
    print_bullet(f"Languages:    {cyan(', '.join(langs))}")
    print_bullet(f"Frameworks:   {cyan(', '.join(fw))}")
    print_bullet(f"Files:        {project_map.structure.total_files} indexed")
    print_bullet(f"Symbols:      {len(symbol_index.symbols)} extracted")
    print_bullet(f"LLM Engine:   {llm_status_str}")

    print("\n" + bold("Git Version Control:"))
    if git_context and git_context.is_git_repo:
        branch_str = cyan(git_context.active_branch)
        dirty_str = red("Dirty (uncommitted changes)") if git_context.is_dirty else green("Clean")
        staged_count = sum(1 for f in git_context.changed_files if f.staged)
        unstaged_count = sum(1 for f in git_context.changed_files if not f.staged)
        print_bullet(f"Branch:       {branch_str}")
        print_bullet(f"Working Tree: {dirty_str}")
        print_bullet(f"Staged Files: {staged_count}")
        print_bullet(f"Modified:     {unstaged_count}")
        print_bullet(f"Untracked:    {len(git_context.untracked_files)}")
    else:
        print_bullet(dim("Not a Git repository"))

    # 4. Quick Intelligence & Verification Scan
    print_info("Evaluating repository health and verifying findings...")
    try:
        orchestrator = IntelligenceOrchestrator(llm_provider=None)
        report = orchestrator.analyze_repository(str(root))

        verifier = VerificationEngine(str(root))
        verified_report = verifier.verify_report(
            report=report,
            project_map=project_map,
            symbol_index=symbol_index,
            filter_false_positives=True,
        )

        p0_count = sum(1 for f in verified_report.findings if (f.priority or "").upper() == "P0")
        p1_count = sum(1 for f in verified_report.findings if (f.priority or "").upper() == "P1")
        p2_count = sum(1 for f in verified_report.findings if (f.priority or "").upper() == "P2")
        p3_count = sum(1 for f in verified_report.findings if (f.priority or "").upper() in ("P3", "P4"))

        print("\n" + bold("Repository Health & Findings:"))
        print_bullet(f"Health Score: {format_health_score(report.health_score)}")
        print_bullet(f"Total Active Findings: {len(verified_report.findings)}")

        table_rows = [
            ["P0 Critical", str(p0_count), "Immediate fix required (breaks gate)" if p0_count > 0 else "None"],
            ["P1 High", str(p1_count), "Remediation recommended" if p1_count > 0 else "None"],
            ["P2 Medium", str(p2_count), "Scheduled maintenance" if p2_count > 0 else "None"],
            ["P3/P4 Low", str(p3_count), "Informational" if p3_count > 0 else "None"],
        ]
        print("")
        print_table(["Severity", "Count", "Action Guidance"], table_rows)

    except Exception as error:
        print_warning(f"Could not compute full findings status: {error}")
