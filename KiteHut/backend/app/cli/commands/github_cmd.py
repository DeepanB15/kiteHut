"""
`kitehut github` subcommands.
Evaluates Quality Gates, reviews Pull Requests, and checks GitHub integration.
"""

from pathlib import Path
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
from app.context.project_map.project_map import ProjectMapBuilder
from app.github.models.github_models import PRFileChange, PullRequestInfo
from app.github.pr_analyzer import PullRequestAnalyzer
from app.github.quality_gate import QualityGateEvaluator
from app.intelligence.orchestrator.orchestrator import IntelligenceOrchestrator
from app.verification.verification_engine import VerificationEngine


@click.group(name="github")
def github_group():
    """GitHub integration, Pull Request analysis, and Quality Gate checks."""
    pass


@github_group.command(name="check")
@click.option(
    "--path",
    "-p",
    "repo_path",
    default=".",
    type=click.Path(exists=True, file_okay=False, dir_okay=True, readable=True),
    help="Target repository directory path.",
)
def github_check_command(repo_path: str):
    """Evaluate repository against CI/CD Quality Gate rules."""
    root = Path(repo_path).resolve()
    print_header(f"GitHub Quality Gate Check -- {root.name}")

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

        quality_gate = QualityGateEvaluator()
        gate_result = quality_gate.evaluate(
            findings=verified_report.findings,
            tests_passed=True,
        )

        if gate_result.passed:
            print_success(bold("Quality Gate Status: PASSED"))
            print_bullet(f"Zero blocking P0/P1 issues found.")
        else:
            print_error(bold("Quality Gate Status: FAILED"))
            for r in gate_result.reasons:
                print(f"  {red('* ' + r)}")

    except Exception as error:
        print_error(f"Failed to evaluate Quality Gate: {error}")


@github_group.command(name="pr")
@click.argument("pr_number", type=int)
@click.option(
    "--path",
    "-p",
    "repo_path",
    default=".",
    type=click.Path(exists=True, file_okay=False, dir_okay=True, readable=True),
    help="Target repository directory path.",
)
def github_pr_command(pr_number: int, repo_path: str):
    """Simulate or execute local PR analysis and review comment generation."""
    root = Path(repo_path).resolve()
    print_header(f"Simulating PR #{pr_number} Analysis")

    try:
        analyzer = PullRequestAnalyzer(str(root))
        pr_info = PullRequestInfo(
            number=pr_number,
            title=f"Pull Request #{pr_number}",
            head_sha="head_sha_local",
            base_sha="base_sha_local",
            author="developer",
        )

        # Map working tree diff
        sample_changes = [
            PRFileChange(
                file_path="src/main.py",
                status="modified",
                additions=5,
                deletions=2,
            )
        ]

        report = analyzer.analyze_pull_request(
            pr_info=pr_info,
            changed_files=sample_changes,
        )

        print(report.summary_markdown)

    except Exception as error:
        print_error(f"PR analysis failed: {error}")
