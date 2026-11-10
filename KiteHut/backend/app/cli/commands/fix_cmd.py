"""
`kitehut fix` command.
Autonomously plans, previews, applies, tests, and verifies remediation for a finding.
"""

from pathlib import Path
import click

from app.action.loop.remediation_loop import ActionRemediationLoop
from app.agent.permissions.policies import DecisionType, PermissionRequest
from app.cli.ui import (
    SYM_CHECK,
    SYM_CROSS,
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
    priority_badge,
    red,
    truth_status_badge,
    yellow,
)
from app.context.project_map.project_map import ProjectMapBuilder
from app.intelligence.orchestrator.orchestrator import IntelligenceOrchestrator
from app.verification.verification_engine import VerificationEngine


@click.command(name="fix")
@click.argument("finding_id", required=True)
@click.option(
    "--path",
    "-p",
    "repo_path",
    default=".",
    type=click.Path(exists=True, file_okay=False, dir_okay=True, readable=True),
    help="Target repository directory path.",
)
@click.option(
    "--yes",
    "-y",
    "auto_approve",
    is_flag=True,
    help="Automatically approve file modifications without interactive prompt.",
)
@click.option(
    "--no-tests",
    is_flag=True,
    help="Skip running tests after applying the remediation patch.",
)
def fix_command(finding_id: str, repo_path: str, auto_approve: bool, no_tests: bool):
    """Autonomously remediate a finding (Plan -> Patch -> Test -> Verify -> Lifecycle)."""
    root = Path(repo_path).resolve()
    print_header(f"KiteHut Autonomous Remediation -- Finding {finding_id}")

    # 1. Discover findings
    print_info("Locating target finding in repository context...")
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
        print_error(f"Failed to scan repository: {error}")
        return

    # 2. Find target finding
    target = next((f for f in findings if f.finding_id == finding_id or finding_id in f.finding_id), None)
    if not target:
        print_error(f"Finding ID '{finding_id}' not found. Run 'kitehut findings' to view active IDs.")
        return

    print_bullet(f"Found Target:  {bold(target.title)}")
    print_bullet(f"Priority:      {priority_badge(target.priority)}")
    print_bullet(f"File Location: {cyan(target.file_path or 'General')}:{target.line_number or 1}")

    # 3. Interactive confirmation callback if not auto_approve
    def interactive_approval(req: PermissionRequest) -> DecisionType:
        if auto_approve:
            return DecisionType.ALLOW
        print("\n" + yellow(bold("Permission Request:")))
        print(f"  Action: {req.tool_name} ({req.permission_type.value})")
        print(f"  Description: {req.description}")
        confirm = click.confirm("Apply this patch to your repository?", default=True)
        return DecisionType.ALLOW if confirm else DecisionType.DENY

    remediation_loop = ActionRemediationLoop(str(root))
    remediation_loop.permission_manager.approval_callback = interactive_approval

    print_info("Generating fix plan, patch, and running remediation loop...")
    result = remediation_loop.remediate_finding(
        finding=target,
        auto_approve=auto_approve,
        run_tests=not no_tests,
    )

    if result.success:
        print("\n" + green(bold(f"{SYM_CHECK} Finding successfully remediated and verified!")))
        print_bullet(f"Message:     {result.message}")
        print_bullet(f"Status:      {green('RESOLVED')}")
        if result.applied_patch and result.applied_patch.file_patches:
            print_bullet(f"Files Modified: {', '.join([fp.file_path for fp in result.applied_patch.file_patches])}")
        if result.test_result:
            test_status = green("PASSED") if result.test_result.passed else red("FAILED")
            print_bullet(f"Test Suite:  {test_status} ({result.test_result.passed_count} passed)")
        print("\n" + dim("Run 'kitehut git commit' to commit these verified fixes."))
    else:
        print("\n" + red(bold(f"{SYM_CROSS} Remediation could not be completed:")))
        print_bullet(f"Reason: {result.message or result.error}")
        if result.test_result and not result.test_result.passed:
            print_warning("Changes were automatically rolled back due to test failure.")
