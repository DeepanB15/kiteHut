"""
Code Quality Agent Prompts.
"""

QUALITY_SYSTEM_PROMPT = """You are the Code Quality Analysis Agent for RepoLens.

Your job is to analyze the maintainability and engineering quality of a repository.

RULES:
- Analyze ONLY the provided repository context and file contents.
- Focus on: code organization, complexity, duplication, naming, error handling, 
  maintainability, separation of concerns.
- Be specific. Bad: "code quality is poor." 
  Good: "The service module contains multiple unrelated responsibilities."
- Do NOT invent quality issues not evidenced in the code.
- Return ONLY valid JSON matching the required schema.

OUTPUT SCHEMA (JSON):
{
  "quality_summary": "overall quality assessment",
  "strengths": ["code quality strengths"],
  "potential_issues": ["potential quality issues"],
  "maintainability_observations": ["observations about maintainability"],
  "refactoring_candidates": ["code areas that may benefit from refactoring"]
}"""


def build_quality_prompt(
    context_data: dict,
    recon_summary: str,
) -> str:
    """Build the user prompt for the Quality Agent."""

    prompt_parts = []

    prompt_parts.append("=== CODE QUALITY ANALYSIS REQUEST ===\n")
    prompt_parts.append(f"Repository: {context_data['repository_summary']}\n")

    # Recon summary
    prompt_parts.append(f"\n=== RECON ANALYSIS ===\n{recon_summary}")

    # Directory tree
    prompt_parts.append("\n\n=== DIRECTORY STRUCTURE ===")
    prompt_parts.append(context_data["directory_tree"])

    # Structure
    structure = context_data["structure"]
    if structure["source_directories"]:
        prompt_parts.append(
            f"\n\n=== SOURCE DIRECTORIES ===\n"
            + "\n".join(f"  - {d}" for d in structure["source_directories"])
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
        "Analyze the code quality of this repository and return your analysis as JSON."
    )

    return "\n".join(prompt_parts)
