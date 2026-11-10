"""
`kitehut start` command.
Launches the continuous repository Guardian, status dashboard, and interactive Agent chat REPL.
"""

from pathlib import Path
import sys
import time
import click

from app.agent.runtime.core import AgentCore
from app.cli.ui import (
    SYM_BULLET,
    SYM_CHECK,
    SYM_CROSS,
    SYM_WARN,
    bold,
    cyan,
    dim,
    format_health_score,
    green,
    print_banner,
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
from app.intelligence.orchestrator.orchestrator import IntelligenceOrchestrator
from app.llm.factory import create_llm_provider
from app.monitoring.watcher import RepoWatcher
from app.verification.verification_engine import VerificationEngine


@click.command(name="start")
@click.option(
    "--path",
    "-p",
    "repo_path",
    default=".",
    type=click.Path(exists=True, file_okay=False, dir_okay=True, readable=True),
    help="Target repository directory path.",
)
@click.option(
    "--watch/--no-watch",
    default=True,
    help="Enable continuous filesystem and Git monitoring.",
)
@click.option(
    "--interactive/--no-interactive",
    default=True,
    help="Launch interactive Agent REPL prompt.",
)
def start_command(repo_path: str, watch: bool, interactive: bool):
    """Start KiteHut Guardian & Interactive Agent Runtime."""
    root = Path(repo_path).resolve()
    print_banner()

    # 1. Quick initial scan
    try:
        builder = ProjectMapBuilder(str(root))
        project_map, symbol_index, import_graph = builder.build()

        orchestrator = IntelligenceOrchestrator(llm_provider=None)
        raw_report = orchestrator.analyze_repository(str(root))

        verifier = VerificationEngine(str(root))
        verified_report = verifier.verify_report(
            report=raw_report,
            project_map=project_map,
            symbol_index=symbol_index,
            import_graph=import_graph,
            filter_false_positives=True,
        )
        finding_count = len(verified_report.findings)
    except Exception as error:
        print_error(f"Initialization error: {error}")
        finding_count = 0
        project_map = None

    # 2. LLM Info
    try:
        llm = create_llm_provider()
        model_name = getattr(llm, "model", "qwen3:4b")
        model_status = green(model_name) if hasattr(llm, "is_available") and llm.is_available() else yellow(f"{model_name} (offline)")
    except Exception:
        model_status = yellow("Ollama not reachable")

    # 3. Print Startup Dashboard Box
    file_count_str = str(project_map.file_count) if project_map else "Unknown"
    monitoring_str = green(f"{SYM_BULLET} Monitoring (Active)") if watch else dim("Monitoring Disabled")

    print(f"{bold('Repository:')}    {cyan(root.name)}")
    print(f"{bold('Model:')}         {model_status}")
    print(f"{bold('Status:')}        {monitoring_str}")
    print(f"{bold('Files:')}         {file_count_str} indexed")
    print(f"{bold('Open findings:')} {yellow(str(finding_count))}")
    print(f"{bold('Agent:')}         {green(bold('READY'))}")
    print(dim("--------------------------------------------------"))

    if not interactive:
        if watch:
            print_info("Running continuous watcher in background. Press Ctrl+C to stop.")
            watcher = RepoWatcher(str(root))
            try:
                while True:
                    rep = watcher.check_once()
                    if rep.changed_events:
                        print("\n" + yellow(f"{SYM_WARN} Changes detected in {len(rep.changed_events)} files:"))
                        for ch in rep.changed_events:
                            print(f"  {cyan(SYM_BULLET)} {ch.file_path} ({ch.change_type.value})")
                        if rep.new_findings:
                            print(red(f"  Discovered {len(rep.new_findings)} new verified findings!"))
                    time.sleep(2)
            except KeyboardInterrupt:
                print()
                print_info("Guardian stopped.")
        return

    # 4. Interactive Agent REPL Loop
    agent_core = AgentCore()
    print_info("Type any development task or question. Type /help for commands, /exit to quit.")

    while True:
        try:
            prompt = click.prompt(f"\n{green(bold('kitehut'))} {cyan('>')}", prompt_suffix=" ").strip()
            if not prompt:
                continue

            if prompt in ("/exit", "/quit", "exit", "quit"):
                print_info("Exiting KiteHut. Goodbye!")
                break

            elif prompt == "/help":
                print("\n" + bold("Available Interactive Commands:"))
                print_bullet("/review       - Run full intelligence review & Quality Gate check")
                print_bullet("/findings     - List all verified active findings")
                print_bullet("/status       - Show repository context, stack, and Git status")
                print_bullet("/fix <ID>     - Autonomously plan and apply a fix")
                print_bullet("/doctor       - Run environment diagnostics")
                print_bullet("/exit         - Quit KiteHut session")
                continue

            elif prompt.startswith("/fix"):
                parts = prompt.split()
                if len(parts) < 2:
                    print_warning("Usage: /fix <finding_id>")
                else:
                    from app.cli.commands.fix_cmd import fix_command
                    ctx = click.Context(fix_command)
                    ctx.invoke(fix_command, finding_id=parts[1], repo_path=str(root), auto_approve=False, no_tests=False)
                continue

            elif prompt == "/review":
                from app.cli.commands.review_cmd import review_command
                ctx = click.Context(review_command)
                ctx.invoke(review_command, repo_path=str(root), diff_only=False)
                continue

            elif prompt == "/findings":
                from app.cli.commands.findings_cmd import findings_command
                ctx = click.Context(findings_command)
                ctx.invoke(findings_command, repo_path=str(root), priority_filter="ALL", category_filter="ALL", finding_id=None)
                continue

            elif prompt == "/status":
                from app.cli.commands.status_cmd import status_command
                ctx = click.Context(status_command)
                ctx.invoke(status_command, repo_path=str(root))
                continue

            elif prompt == "/doctor":
                from app.cli.commands.doctor_cmd import doctor_command
                ctx = click.Context(doctor_command)
                ctx.invoke(doctor_command, repo_path=str(root))
                continue

            # Default: execute agent goal
            from app.cli.commands.ask_cmd import ask_command
            ctx = click.Context(ask_command)
            ctx.invoke(ask_command, prompt=prompt, repo_path=str(root), auto_approve=False)

        except (KeyboardInterrupt, EOFError):
            print()
            print_info("Session ended.")
            break
        except Exception as error:
            print_error(f"Error: {error}")
