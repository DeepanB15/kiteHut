"""
`kitehut report` command.
Generates comprehensive repository intelligence and verification reports in Markdown or JSON.
"""

import json
from pathlib import Path
from typing import Optional
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
    print_success,
    print_warning,
    red,
)
from app.context.git.git_context import GitContextExtractor
from app.context.project_map.project_map import ProjectMapBuilder
from app.github.quality_gate import QualityGateEvaluator
from app.intelligence.orchestrator.orchestrator import IntelligenceOrchestrator
from app.verification.verification_engine import VerificationEngine


@click.command(name="report")
@click.option(
    "--path",
    "-p",
    "repo_path",
    default=".",
    type=click.Path(exists=True, file_okay=False, dir_okay=True, readable=True),
    help="Target repository directory path.",
)
@click.option(
    "--format",
    "-f",
    "output_format",
    type=click.Choice(["markdown", "json"], case_sensitive=False),
    default="markdown",
    help="Report output format (default: markdown).",
)
@click.option(
    "--output",
    "-o",
    "output_file",
    default=None,
    help="Save report to specified file path instead of stdout.",
)
def report_command(repo_path: str, output_format: str, output_file: Optional[str]):
    """Generate a comprehensive repository intelligence and security audit report."""
    root = Path(repo_path).resolve()
    print_info(f"Generating {output_format.upper()} report for {root.name}...")

    # 1. Gather all repository context & analysis
    try:
        builder = ProjectMapBuilder(str(root))
        project_map, symbol_index, import_graph = builder.build()

        git_extractor = GitContextExtractor(str(root))
        git_context = git_extractor.extract()

        orchestrator = IntelligenceOrchestrator(llm_provider=None)
        raw_report = orchestrator.analyze_repository(str(root))

        verifier = VerificationEngine(str(root))
        verified_report = verifier.verify_report(
            report=raw_report,
            project_map=project_map,
            symbol_index=symbol_index,
            import_graph=import_graph,
            git_context=git_context,
            filter_false_positives=True,
        )

        quality_gate = QualityGateEvaluator()
        gate_result = quality_gate.evaluate(findings=verified_report.findings, tests_passed=True)

    except Exception as error:
        print_error(f"Failed to generate intelligence report: {error}")
        return

    # 2. Format Output
    langs = list(project_map.structure.languages.keys()) if project_map.structure.languages else ["Unknown"]
    fw = [t.name for t in project_map.technologies] if project_map.technologies else ["None"]
    file_count = project_map.structure.total_files

    if output_format.lower() == "json":
        data = {
            "repository": root.name,
            "path": str(root),
            "health_score": raw_report.health_score,
            "quality_gate": {
                "passed": gate_result.passed,
                "reasons": gate_result.reasons,
            },
            "languages": langs,
            "frameworks": fw,
            "file_count": file_count,
            "total_findings": len(verified_report.findings),
            "findings": [
                {
                    "id": f.finding_id,
                    "title": f.title,
                    "priority": f.priority,
                    "category": f.category.value if hasattr(f.category, "value") else str(f.category),
                    "severity": f.severity.value if hasattr(f.severity, "value") else str(f.severity),
                    "file_path": f.file_path,
                    "line_number": f.line_number,
                    "truth_status": f.truth_status,
                    "confidence": f.confidence,
                    "description": f.description,
                    "recommendation": f.recommendation,
                }
                for f in verified_report.findings
            ],
        }
        rendered = json.dumps(data, indent=2)

    else:
        # Markdown Report
        lines = [
            f"# KiteHut Audit Report -- {root.name}",
            f"**Generated:** `{raw_report.timestamp.isoformat()}`  ",
            f"**Repository Health:** `{raw_report.health_score:.1f} / 100`  ",
            f"**Quality Gate:** `{'PASSED' if gate_result.passed else 'FAILED'}`  ",
            "",
            "## 1. Project Overview",
            f"- **Languages:** {', '.join(langs)}",
            f"- **Frameworks:** {', '.join(fw)}",
            f"- **Files Indexed:** {file_count}",
            f"- **Total Findings:** {len(verified_report.findings)}",
            "",
            "## 2. Quality Gate Status",
            f"Result: **{'PASSED' if gate_result.passed else 'FAILED'}**",
        ]
        if gate_result.reasons:
            for r in gate_result.reasons:
                lines.append(f"- {r}")

        lines.extend(["", "## 3. Verified Findings Breakdown", ""])
        if not verified_report.findings:
            lines.append("No verified security, architecture, or quality issues detected.")
        else:
            for i, f in enumerate(verified_report.findings, 1):
                lines.append(f"### {i}. [{f.priority or 'P3'}] {f.title}")
                lines.append(f"- **Category:** `{f.category.value if hasattr(f.category, 'value') else str(f.category)}`")
                lines.append(f"- **Location:** `{f.file_path or 'repo'}`:{f.line_number or 1}")
                lines.append(f"- **Truth Status:** `{f.truth_status}` (Confidence: {f.confidence:.1f}%)")
                if f.description:
                    lines.append(f"- **Description:** {f.description}")
                if f.code_snippet:
                    lines.append("```python")
                    lines.append(f.code_snippet)
                    lines.append("```")
                if f.recommendation:
                    lines.append(f"- **Recommendation:** {f.recommendation}")
                lines.append("")

        lines.extend([
            "---",
            "*Report generated locally by KiteHut -- Autonomous AI Engineering Agent.*",
        ])
        rendered = "\n".join(lines)

    # 3. Output
    if output_file:
        out_p = Path(output_file).resolve()
        out_p.write_text(rendered, encoding="utf-8")
        print_success(f"Report saved to: {out_p}")
    else:
        print("\n" + rendered)
