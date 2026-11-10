"""
Security Agent Prompts.
"""

SECURITY_SYSTEM_PROMPT = """You are the Security Analysis Agent for RepoLens.

Your job is to identify potential security concerns in a software repository.

IMPORTANT: Your findings are POTENTIAL RISKS, not confirmed vulnerabilities.
Do not claim something is definitively a vulnerability unless the code clearly shows it.

RULES:
- Analyze ONLY the provided repository context and file contents.
- Look for: hardcoded secrets, authentication issues, input validation, 
  dangerous configurations, exposed credentials, insecure patterns.
- Do NOT invent security issues not evidenced in the code.
- If no security issues are found, say so honestly.
- Return ONLY valid JSON matching the required schema.

OUTPUT SCHEMA (JSON):
{
  "security_observations": ["general security observations"],
  "potential_risks": ["potential security risks identified"],
  "security_strengths": ["good security practices found"],
  "areas_for_verification": ["areas needing manual verification"]
}"""


def build_security_prompt(
    context_data: dict,
    recon_summary: str,
) -> str:
    """Build the user prompt for the Security Agent."""

    prompt_parts = []

    prompt_parts.append("=== SECURITY ANALYSIS REQUEST ===\n")
    prompt_parts.append(f"Repository: {context_data['repository_summary']}\n")

    # Recon summary
    prompt_parts.append(f"\n=== RECON ANALYSIS ===\n{recon_summary}")

    # Technology stack
    if context_data["technology_stack"]:
        prompt_parts.append(
            f"\n\n=== TECHNOLOGIES ===\n"
            f"{', '.join(context_data['technology_stack'])}"
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
        "Analyze this repository for potential security concerns and return your analysis as JSON."
    )

    return "\n".join(prompt_parts)
