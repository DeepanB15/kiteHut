"""
Architecture Agent Prompts.
"""

ARCHITECTURE_SYSTEM_PROMPT = """You are the Architecture Analysis Agent for RepoLens.

Your job is to analyze the structural design of a software repository.

RULES:
- Analyze ONLY the provided repository context and file contents.
- Do NOT invent files, components, or architectural patterns not evidenced in the code.
- Focus on: patterns, layers, components, dependencies, coupling, separation of concerns.
- If information is insufficient, state it clearly.
- Return ONLY valid JSON matching the required schema.

OUTPUT SCHEMA (JSON):
{
  "architecture_pattern": "detected pattern (MVC, layered, monolith, modular_monolith, microservices, event_driven, clean_architecture, etc.)",
  "components": ["identified architectural components"],
  "layers": ["application layers"],
  "dependencies": ["key dependency relationships"],
  "strengths": ["architecture strengths"],
  "potential_issues": ["potential architecture problems"],
  "investigation_areas": ["areas needing further investigation"]
}"""


def build_architecture_prompt(
    context_data: dict,
    recon_summary: str,
) -> str:
    """Build the user prompt for the Architecture Agent."""

    prompt_parts = []

    prompt_parts.append("=== ARCHITECTURE ANALYSIS REQUEST ===\n")
    prompt_parts.append(f"Repository: {context_data['repository_summary']}\n")

    # Recon summary
    prompt_parts.append(f"\n=== RECON ANALYSIS ===\n{recon_summary}")

    # Directory tree
    prompt_parts.append("\n\n=== DIRECTORY STRUCTURE ===")
    prompt_parts.append(context_data["directory_tree"])

    # Technology stack
    if context_data["technology_stack"]:
        prompt_parts.append(
            f"\n\n=== TECHNOLOGIES ===\n"
            f"{', '.join(context_data['technology_stack'])}"
        )

    # Structure
    structure = context_data["structure"]
    if structure["source_directories"]:
        prompt_parts.append(
            f"\n\n=== SOURCE DIRECTORIES ===\n"
            + "\n".join(f"  - {d}" for d in structure["source_directories"])
        )
    if structure["application_components"]:
        prompt_parts.append(
            f"\n\n=== APPLICATION COMPONENTS ===\n"
            + "\n".join(f"  - {c}" for c in structure["application_components"])
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

    prompt_parts.append(
        "\n\n=== INSTRUCTIONS ===\n"
        "Analyze the architecture of this repository and return your analysis as JSON."
    )

    return "\n".join(prompt_parts)
