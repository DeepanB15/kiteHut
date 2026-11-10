"""
`kitehut findings` command.
Lists and inspects verified repository findings with ground-truth evidence.
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
    print_table,
    print_warning,
    priority_badge,
    red,
    truth_status_badge,
    yellow,
)
from app.context.project_map.project_map import ProjectMapBuilder
from app.intelligence.models.findings import FindingCategory
from app.intelligence.orchestrator.orchestrator import IntelligenceOrchestrator
from app.verification.verification_engine import VerificationEngine


@click.command(name="findings")
@click.option(
    "--path",
    "-p",
    "repo_path",
    default=".",
    type=click.Path(exists=True, file_okay=False, dir_okay=True, readable=True),
    help="Target repository directory path.",
)
@click.option(
    "--priority",
    "-P",
    "priority_filter",
    type=click.Choice(["P0", "P1", "P2", "P3", "P4", "ALL"], case_sensitive=False),
    default="ALL",
    help="Filter findings by priority level.",
)
@click.option(
    "--category",
    "-c",
    "category_filter",
    type=click.Choice(
        ["security", "architecture", "testing", "quality", "configuration", "dependency", "api", "code_review", "ALL"],
        case_sensitive=False,
    ),
    default="ALL",
    help="Filter findings by specialist category.",
)
@click.option(
    "--inspect",
    "-i",
    "finding_id",
    default=None,
    help="Deeply inspect finding with atomic claims, evidence, and remediation plan.",
)
def findings_command(
    repo_path: str,
    priority_filter: str,
    category_filter: str,
    finding_id: Optional[str],
):
    """List, filter, and inspect verified repository findings."""
    root = Path(repo_path).resolve()

    # 1. Run Intelligence & Verification scan
    try:
        builder = ProjectMapBuilder(str(root))
        project_map, symbol_index, import_graph = builder.build()

        orchestrator = IntelligenceOrchestrator(llm_provider=None)
        report = orchestrator.analyze_repository(str(root))

        verifier = VerificationEngine(str(root))
        verified_report = verifier.verify_report(
            report=report,
            project_map=project_map,
            symbol_index=symbol_index,
            import_graph=import_graph,
            filter_false_positives=True,
        )
        findings = verified_report.findings
    except Exception as error:
        print_error(f"Failed to scan repository findings: {error}")
        return

    # 2. Inspect single finding if requested
    if finding_id:
        target = next((f for f in findings if f.finding_id == finding_id or finding_id in f.finding_id), None)
        if not target:
            print_error(f"Finding ID '{finding_id}' not found in active repository findings.")
            return

        print_header(f"Finding Inspection -- {target.finding_id}")
        print_bullet(f"Title:         {bold(target.title)}")
        print_bullet(f"Priority:      {priority_badge(target.priority)}")
        print_bullet(f"Category:      {cyan(target.category.value if hasattr(target.category, 'value') else str(target.category))}")
        print_bullet(f"Severity:      {target.severity.value if hasattr(target.severity, 'value') else str(target.severity)}")
        print_bullet(f"Truth Status:  {truth_status_badge(target.truth_status)}")
        print_bullet(f"Confidence:    {target.confidence:.1f}%")
        print_bullet(f"File Location: {cyan(target.file_path or 'General')}:{target.line_number or 1}")

        if target.description:
            print("\n" + bold("Description:"))
            print(f"  {target.description}")

        if target.code_snippet:
            print("\n" + bold("Code Snippet:"))
            for line in target.code_snippet.splitlines():
                print(f"  {dim('|')} {line}")

        if target.evidence_summary or target.evidence:
            print("\n" + bold("Ground-Truth Evidence:"))
            if target.evidence_summary:
                print(f"  {target.evidence_summary}")
            for ev in getattr(target, "evidence", []):
                print_bullet(f"{ev.source_file}:{ev.line_number} -- {ev.description}")

        if target.recommendation:
            print("\n" + bold("Suggested Remediation:"))
            print(f"  {green(target.recommendation)}")

        print("\n" + dim(f"Run 'kitehut fix {target.finding_id}' to autonomously apply remediation."))
        return

    # 3. Filter Findings
    filtered = findings
    if priority_filter.upper() != "ALL":
        filtered = [f for f in filtered if (f.priority or "").upper() == priority_filter.upper()]

    if category_filter.upper() != "ALL":
        filtered = [
            f for f in filtered
            if (f.category.value if hasattr(f.category, "value") else str(f.category)).lower() == category_filter.lower()
        ]

    print_header(f"Verified Findings ({len(filtered)} matching)")

    if not filtered:
        print_success("No findings match the specified criteria. Repository is clean!")
        return

    headers = ["ID", "Priority", "Category", "Location", "Title", "Truth"]
    rows = []
    for f in filtered:
        cat_str = f.category.value if hasattr(f.category, "value") else str(f.category)
        loc = f"{f.file_path}:{f.line_number}" if f.file_path and f.line_number else (f.file_path or "repo")
        if len(loc) > 28:
            loc = "..." + loc[-25:]
        title = f.title[:38] + "..." if len(f.title) > 38 else f.title
        rows.append([
            f.finding_id[:10],
            f.priority or "P3",
            cat_str,
            loc,
            title,
            f.truth_status or "VERIFIED",
        ])

    print_table(headers, rows)
    print("\n" + dim("Use 'kitehut findings --inspect <ID>' to view deep evidence and remediation steps."))
