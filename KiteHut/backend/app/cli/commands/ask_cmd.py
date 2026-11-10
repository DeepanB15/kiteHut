"""
`kitehut ask` command.
Directs natural-language engineering questions and tasks to the Agent Core.
"""

from pathlib import Path
import click

from app.agent.permissions.policies import DecisionType, PermissionRequest
from app.agent.runtime.core import AgentCore
from app.agent.state.agent_state import TaskStatus
from app.cli.ui import (
    SYM_ARROW,
    SYM_CHECK,
    SYM_CROSS,
    SYM_LOCK,
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
from app.llm.factory import create_llm_provider


@click.command(name="ask")
@click.argument("prompt", required=True)
@click.option(
    "--path",
    "-p",
    "repo_path",
    default=".",
    type=click.Path(exists=True, file_okay=False, dir_okay=True, readable=True),
    help="Target repository directory path.",
)
@click.option(
    "--auto-approve",
    "-y",
    is_flag=True,
    help="Auto-approve all agent tool executions (including writes).",
)
def ask_command(prompt: str, repo_path: str, auto_approve: bool):
    """Ask KiteHut a natural-language question or assign an engineering task."""
    root = Path(repo_path).resolve()
    print_header("KiteHut Agent -- Task Execution")
    print(bold("Goal: ") + cyan(prompt))

    # 1. Setup interactive approval callback
    def interactive_approval_callback(req: PermissionRequest) -> DecisionType:
        if auto_approve:
            return DecisionType.ALLOW
        print("\n" + yellow(bold(f"{SYM_LOCK} Agent Permission Request:")))
        print(f"  Tool:        {cyan(req.tool_name)}")
        print(f"  Action:      {req.description}")
        print(f"  Risk Level:  {req.risk_level.value}")
        confirm = click.confirm("Allow tool execution?", default=True)
        return DecisionType.ALLOW if confirm else DecisionType.DENY

    # 2. Setup event progress logger
    def event_logger(event_name: str, payload: dict):
        if event_name == "step_start":
            step_num = payload.get("step_number", 1)
            tool_name = payload.get("tool_name", "")
            print(f"  {cyan(SYM_ARROW)} Step {step_num}: Executing {bold(tool_name)}...")
        elif event_name == "tool_result":
            success = payload.get("success", True)
            if success:
                print(f"  {green(SYM_CHECK)} Tool execution completed.")
            else:
                print(f"  {red(SYM_CROSS)} Tool reported error: {payload.get('error')}")

    # 3. Initialize AgentCore
    try:
        agent_core = AgentCore()
    except Exception as error:
        print_error(f"Failed to initialize Agent Core: {error}")
        return

    print_info("Planning task and selecting repository context...")

    try:
        state = agent_core.create_task(
            repository_path=str(root),
            user_goal=prompt,
            approval_callback=interactive_approval_callback,
            auto_allow_safe=True,
            auto_allow_all=auto_approve,
        )

        final_state = agent_core.run_task(
            task_id=state.task_id,
            event_callback=event_logger,
        )

        # 4. Display Output
        print("\n" + bold("Agent Response:"))
        if final_state.final_answer:
            print(final_state.final_answer)
        elif final_state.error:
            print_error(f"Agent stopped with error: {final_state.error}")
        else:
            print_info(f"Task completed with status: {final_state.status.value}")

        if final_state.status == TaskStatus.COMPLETED:
            print("\n" + green(bold(f"{SYM_CHECK} Task executed successfully.")))
        elif final_state.status == TaskStatus.AWAITING_APPROVAL:
            print("\n" + yellow("Task paused awaiting permission approval."))
        elif final_state.status == TaskStatus.FAILED:
            print("\n" + red(bold(f"{SYM_CROSS} Task execution failed.")))

    except Exception as error:
        print_error(f"Error during agent task execution: {error}")
