"""
Testing Agent Prompts.
"""

TESTING_SYSTEM_PROMPT = """You are the Testing Analysis Agent for RepoLens.

Your job is to evaluate the testing maturity of a repository.

RULES:
- Analyze ONLY the provided repository context and file contents.
- Look for: test directories, test files, test frameworks, test patterns.
- Determine testing maturity: none, low, medium, high.
- Identify tested and potentially untested components.
- Do NOT invent test files or frameworks not present in the repository.
- Return ONLY valid JSON matching the required schema.

OUTPUT SCHEMA (JSON):
{
  "test_frameworks": ["detected test frameworks"],
  "test_types": ["types of tests found: unit, integration, e2e"],
  "testing_maturity": "none|low|medium|high",
  "tested_components": ["components with tests"],
  "potentially_untested_components": ["components without visible tests"],
  "observations": ["testing-related observations"]
}"""


def build_testing_prompt(
    context_data: dict,
    recon_summary: str,
) -> str:
    """Build the user prompt for the Testing Agent."""

    prompt_parts = []

    prompt_parts.append("=== TESTING ANALYSIS REQUEST ===\n")
    prompt_parts.append(f"Repository: {context_data['repository_summary']}\n")

    # Recon summary
    prompt_parts.append(f"\n=== RECON ANALYSIS ===\n{recon_summary}")

    # Directory tree
    prompt_parts.append("\n\n=== DIRECTORY STRUCTURE ===")
    prompt_parts.append(context_data["directory_tree"])

    # Structure
    structure = context_data["structure"]
    if structure["test_directories"]:
        prompt_parts.append(
            f"\n\n=== TEST DIRECTORIES ===\n"
            + "\n".join(f"  - {d}" for d in structure["test_directories"])
        )
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
        "Analyze the testing maturity of this repository and return your analysis as JSON."
    )

    return "\n".join(prompt_parts)
