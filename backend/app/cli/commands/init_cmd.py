"""
`kitehut init` command.
Initializes KiteHut configuration and project index for a repository.
"""

import json
from pathlib import Path
import click

from app.cli.ui import (
    bold,
    cyan,
    dim,
    green,
    print_banner,
    print_bullet,
    print_error,
    print_header,
    print_info,
    print_success,
    print_warning,
)
from app.context.project_map.project_map import ProjectMapBuilder


@click.command(name="init")
@click.option(
    "--path",
    "-p",
    "repo_path",
    default=".",
    type=click.Path(exists=True, file_okay=False, dir_okay=True, readable=True),
    help="Target repository directory path (default: current directory).",
)
@click.option(
    "--model",
    "-m",
    default="qwen3:4b",
    help="Default local LLM model name (default: qwen3:4b).",
)
@click.option(
    "--force",
    "-f",
    is_flag=True,
    help="Overwrite existing .kitehut.json configuration.",
)
def init_command(repo_path: str, model: str, force: bool):
    """Initialize KiteHut configuration, inspect technology stack, and index the repository."""
    root = Path(repo_path).resolve()
    print_header(f"Initializing KiteHut for {root.name}")

    config_file = root / ".kitehut.json"
    if config_file.exists() and not force:
        print_warning(f"Repository already initialized. Config exists at: {config_file}")
        print_info("Use --force to re-initialize configuration.")
        return

    # 1. Inspect repository and build ProjectMap
    print_info("Indexing repository structure and detecting technology stack...")
    try:
        builder = ProjectMapBuilder(str(root))
        project_map, symbol_index, import_graph = builder.build()
    except Exception as error:
        print_error(f"Failed to inspect repository: {error}")
        return

    # 2. Extract stack details
    languages = list(project_map.structure.languages.keys()) or ["Unknown"]
    frameworks = [t.name for t in project_map.technologies]
    dependencies = project_map.external_packages
    entrypoints = project_map.entry_points

    # 3. Create default configuration
    config = {
        "version": "2.0",
        "repository_name": root.name,
        "repository_path": str(root),
        "default_model": model,
        "languages": languages,
        "frameworks": frameworks,
        "quality_gates": {
            "max_p0": 0,
            "max_p1": 0,
            "max_security_findings": 0,
            "tests_must_pass": True,
            "confidence_threshold": 70.0,
        },
        "monitoring": {
            "enabled": True,
            "debounce_seconds": 2.0,
            "watch_filesystem": True,
            "watch_git": True,
        },
        "permissions": {
            "auto_allow_safe": True,
            "require_approval_for_modifications": True,
            "require_approval_for_git": True,
        },
    }

    try:
        config_file.write_text(json.dumps(config, indent=2), encoding="utf-8")
        print_success(f"Generated configuration at {config_file.name}")
    except Exception as error:
        print_error(f"Could not write configuration file: {error}")
        return

    # 4. Print Summary
    print("\n" + bold("Repository Summary:"))
    print_bullet(f"Languages:    {cyan(', '.join(languages))}")
    if frameworks:
        print_bullet(f"Frameworks:   {cyan(', '.join(frameworks))}")
    if entrypoints:
        print_bullet(f"Entry Points: {dim(', '.join(entrypoints[:5]))}")
    print_bullet(f"Dependencies: {len(dependencies)} discovered")
    print_bullet(f"Files Indexed: {project_map.structure.total_files}")
    print_bullet(f"Symbols:      {len(symbol_index.symbols)} symbols cataloged")
    print_bullet(f"LLM Model:    {green(model)}")

    print("")
    print_success(bold("KiteHut initialized successfully!"))
    print_info("Run 'kitehut start' to launch continuous monitoring and agent runtime.")
