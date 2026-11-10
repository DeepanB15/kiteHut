"""
AI Recon Agent Prompts.
"""

RECON_SYSTEM_PROMPT = """You are the Reconnaissance Agent for RepoLens.

Your job is to understand a software repository and produce a structured analysis.

RULES:
- Analyze ONLY the provided repository context and file contents.
- Do NOT invent files, components, or features that are not present.
- If information is insufficient, state it as an unknown.
- Separate observations (facts) from assumptions (inferences).
- Return ONLY valid JSON matching the required schema.

OUTPUT SCHEMA (JSON):
{
  "project_summary": "one paragraph summary",
  "project_purpose": "what problem this solves",
  "application_type": "web_api|web_frontend|full_stack|cli_tool|library|machine_learning|data_pipeline|microservice|mobile_application|unknown",
  "architecture_overview": "how the project is organized",
  "major_components": ["list of major components"],
  "entry_points": ["list of entry points"],
  "key_technologies": ["list of key technologies"],
  "observations": ["notable observations"],
  "assumptions": ["assumptions made"],
  "unknowns": ["things that could not be determined"],
  "areas_for_investigation": ["areas needing deeper analysis"]
}"""


def build_recon_prompt(context_data: dict) -> str:
    """Build the user prompt for the AI Recon Agent."""

    prompt_parts = []

    prompt_parts.append("=== REPOSITORY ANALYSIS REQUEST ===\n")
    prompt_parts.append(f"Repository: {context_data['repository_summary']}\n")

    # Directory tree
    prompt_parts.append("\n=== DIRECTORY STRUCTURE ===")
    prompt_parts.append(context_data["directory_tree"])

    # Technology stack
    if context_data["technology_stack"]:
        prompt_parts.append(
            f"\n\n=== TECHNOLOGIES ===\n"
            f"{', '.join(context_data['technology_stack'])}"
        )

    # Languages
    if context_data["languages"]:
        langs = ", ".join(
            f"{lang}: {count}"
            for lang, count in context_data["languages"].items()
        )
        prompt_parts.append(f"\n\n=== LANGUAGES ===\n{langs}")

    # Structure
    structure = context_data["structure"]
    if structure["source_directories"]:
        prompt_parts.append(
            f"\n\n=== SOURCE DIRECTORIES ===\n"
            + "\n".join(f"  - {d}" for d in structure["source_directories"])
        )
    if structure["test_directories"]:
        prompt_parts.append(
            f"\n\n=== TEST DIRECTORIES ===\n"
            + "\n".join(f"  - {d}" for d in structure["test_directories"])
        )

    # Entry points
    if context_data["entry_points"]:
        prompt_parts.append(
            "\n\n=== ENTRY POINTS ===\n"
            + "\n".join(f"  - {ep}" for ep in context_data["entry_points"][:10])
        )

    # Selected file contents
    if context_data["selected_files"]:
        prompt_parts.append("\n\n=== SELECTED FILE CONTENTS ===")
        for file_info in context_data["selected_files"]:
            prompt_parts.append(
                f"\n--- {file_info['path']} ({file_info['category']}) ---"
            )
            prompt_parts.append(file_info["content"][:3000])
            prompt_parts.append("---")

    # Statistics
    stats = context_data["statistics"]
    prompt_parts.append(
        f"\n\n=== STATISTICS ===\n"
        f"Total files: {stats['total_files']}\n"
        f"Total directories: {stats['total_directories']}"
    )

    prompt_parts.append(
        "\n\n=== INSTRUCTIONS ===\n"
        "Analyze the above repository context and return your analysis as JSON."
    )

    return "\n".join(prompt_parts)
