"""
Deterministic Recon Agent.

Analyzes repository context and produces structured recon output.
This agent uses rule-based logic only — no LLM calls.

In Phase 2, this will be upgraded to an AI-powered Recon Agent
that reads key files and generates deeper insights.
"""

from app.graph.state import AnalysisState, ReconResult
from app.models.repository_context import RepositoryContext


# Keywords that hint at application type
APP_TYPE_KEYWORDS = {
    "web_api": ["fastapi", "flask", "django", "express", "spring boot", "rails"],
    "web_frontend": ["react", "vue", "angular", "next.js", "svelte"],
    "cli_tool": ["click", "argparse", "typer", "commander"],
    "library": ["pypi", "npm", "cargo"],
    "mobile": ["react native", "flutter", "swift", "kotlin"],
    "data_science": ["pandas", "numpy", "tensorflow", "pytorch", "jupyter"],
}


def _detect_application_type(context: RepositoryContext) -> str:
    """Infer the application type from detected technologies."""

    technologies_lower = [t.lower() for t in context.technologies]

    for app_type, keywords in APP_TYPE_KEYWORDS.items():
        for keyword in keywords:
            if keyword in technologies_lower:
                return app_type

    # Fallback: infer from languages
    languages = [lang.lower() for lang in context.languages]

    if "python" in languages:
        return "python_project"
    if "javascript" in languages or "typescript" in languages:
        return "javascript_project"
    if "java" in languages:
        return "java_project"
    if "go" in languages:
        return "go_project"
    if "rust" in languages:
        return "rust_project"

    return "unknown"


def _infer_project_purpose(
    context: RepositoryContext,
    app_type: str,
) -> str:
    """Generate a basic purpose description from context."""

    name = context.repository_name
    owner = context.repository_owner
    techs = ", ".join(context.technologies) if context.technologies else "unknown stack"

    type_descriptions = {
        "web_api": "a web API/service",
        "web_frontend": "a web frontend application",
        "cli_tool": "a command-line tool",
        "library": "a reusable library/package",
        "mobile": "a mobile application",
        "data_science": "a data science/ML project",
        "python_project": "a Python project",
        "javascript_project": "a JavaScript/TypeScript project",
        "java_project": "a Java project",
        "go_project": "a Go project",
        "rust_project": "a Rust project",
        "unknown": "a software project",
    }

    desc = type_descriptions.get(app_type, "a software project")

    return f"{owner}/{name} is {desc} built with {techs}."


def _generate_architecture_overview(
    context: RepositoryContext,
) -> str:
    """Generate a basic architecture overview from structure."""

    parts = []

    if context.structure.source_directories:
        parts.append(
            f"Source code in: {', '.join(context.structure.source_directories)}"
        )

    if context.structure.test_directories:
        parts.append(
            f"Tests in: {', '.join(context.structure.test_directories)}"
        )

    if context.structure.frontend_directories:
        parts.append(
            f"Frontend in: {', '.join(context.structure.frontend_directories)}"
        )

    if context.structure.documentation_directories:
        parts.append(
            f"Documentation in: {', '.join(context.structure.documentation_directories[:3])}"
        )

    if context.structure.application_components:
        parts.append(
            f"Components: {', '.join(context.structure.application_components)}"
        )

    if not parts:
        return "Flat project structure with no clearly organized directories detected."

    return ". ".join(parts) + "."


def _collect_observations(
    context: RepositoryContext,
) -> list[str]:
    """Collect deterministic observations from the repository."""

    observations = []

    # File count observations
    total = context.statistics.total_files
    if total < 10:
        observations.append(
            f"Small repository with only {total} files."
        )
    elif total > 1000:
        observations.append(
            f"Large repository with {total} files."
        )

    # Language observations
    if len(context.languages) > 3:
        observations.append(
            f"Multi-language project with {len(context.languages)} languages: "
            + ", ".join(context.languages.keys())
        )

    # Tech observations
    if context.technologies:
        observations.append(
            f"Detected technologies: {', '.join(context.technologies)}"
        )

    # Structure observations
    if not context.structure.source_directories:
        observations.append(
            "No standard source directory (src/, app/, backend/) detected."
        )

    if not context.structure.test_directories:
        observations.append(
            "No test directories detected — testing maturity is unknown."
        )

    if context.entry_points:
        observations.append(
            f"Found {len(context.entry_points)} potential entry point(s)."
        )

    # Documentation observations
    has_readme = any(
        f.category == "documentation"
        for f in context.important_files
    )
    if not has_readme:
        observations.append("No README file detected.")

    return observations


def _collect_unknowns(
    context: RepositoryContext,
) -> list[str]:
    """List things the recon agent cannot determine without AI."""

    unknowns = []

    if not context.entry_points:
        unknowns.append("Entry points could not be determined from file names alone.")

    unknowns.append(
        "Business logic and domain-specific purpose require reading source code."
    )

    unknowns.append(
        "Code quality, complexity, and coupling require deeper analysis."
    )

    return unknowns


def _collect_areas_for_investigation(
    context: RepositoryContext,
) -> list[str]:
    """Suggest areas that future agents should investigate."""

    areas = []

    if not context.structure.test_directories:
        areas.append("Testing — no test directories found, investigate test coverage.")

    if "docker" not in [t.lower() for t in context.technologies]:
        areas.append(
            "Deployment — no Docker configuration detected."
        )

    has_config = any(
        f.category == "configuration"
        for f in context.important_files
    )
    if not has_config:
        areas.append(
            "Configuration — no .env.example or .gitignore detected."
        )

    areas.append(
        "Architecture — require deeper module and dependency analysis."
    )

    areas.append(
        "Security — require security-focused scan."
    )

    return areas


def run_recon_agent(state: AnalysisState) -> AnalysisState:
    """
    Deterministic recon node for the LangGraph workflow.

    Reads the repository context from state and produces
    a structured ReconResult without any LLM calls.
    """

    context = state.get("repository_context")

    if context is None:
        return {
            **state,
            "status": "failed",
            "error": "No repository context available for recon.",
        }

    app_type = _detect_application_type(context)
    purpose = _infer_project_purpose(context, app_type)
    arch_overview = _generate_architecture_overview(context)
    observations = _collect_observations(context)
    unknowns = _collect_unknowns(context)
    areas = _collect_areas_for_investigation(context)

    # Major components = application components + source dirs
    major_components = list(context.structure.application_components)
    if context.structure.source_directories:
        major_components.extend(context.structure.source_directories)

    recon_result: ReconResult = {
        "project_purpose": purpose,
        "application_type": app_type,
        "architecture_overview": arch_overview,
        "major_components": major_components,
        "likely_entry_points": context.entry_points,
        "observations": observations,
        "assumptions": [
            "All detected technologies are actively used.",
            "Directory names accurately reflect their purpose.",
            "Important files represent the project's core configuration.",
        ],
        "unknowns": unknowns,
        "areas_for_investigation": areas,
    }

    print("\n===== RECON RESULT =====")
    print(f"  Purpose: {purpose}")
    print(f"  Type: {app_type}")
    print(f"  Components: {len(major_components)}")
    print(f"  Observations: {len(observations)}")
    print(f"  Areas to investigate: {len(areas)}")
    print("========================\n")

    return {
        **state,
        "recon_result": recon_result,
        "status": "recon",
    }
