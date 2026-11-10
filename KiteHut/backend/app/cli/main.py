"""
RepoLens Master CLI Entry Point.
"""

import sys
import click

from app.cli.commands.ask_cmd import ask_command
from app.cli.commands.doctor_cmd import doctor_command
from app.cli.commands.findings_cmd import findings_command
from app.cli.commands.fix_cmd import fix_command
from app.cli.commands.git_cmd import git_group
from app.cli.commands.github_cmd import github_group
from app.cli.commands.init_cmd import init_command
from app.cli.commands.models_cmd import models_command
from app.cli.commands.report_cmd import report_command
from app.cli.commands.review_cmd import review_command
from app.cli.commands.start_cmd import start_command
from app.cli.commands.status_cmd import status_command


@click.group(
    name="repolens",
    help="RepoLens -- Local AI Engineering Agent & Continuous Guardian.",
    context_settings={"help_option_names": ["-h", "--help"]},
)
@click.version_option(version="2.0.0", prog_name="repolens")
def cli():
    """RepoLens: Understand, inspect, modify, test, verify, and continuously monitor repositories."""
    pass


# Register all subcommands
cli.add_command(init_command)
cli.add_command(start_command)
cli.add_command(ask_command)
cli.add_command(review_command)
cli.add_command(fix_command)
cli.add_command(status_command)
cli.add_command(findings_command)
cli.add_command(report_command)
cli.add_command(git_group)
cli.add_command(github_group)
cli.add_command(models_command)
cli.add_command(doctor_command)


def main():
    """Main entrypoint function for setup.py or direct execution."""
    cli()


if __name__ == "__main__":
    main()
