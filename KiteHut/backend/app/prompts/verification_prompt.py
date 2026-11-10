"""
Verification Agent Prompts.

Prompts for optional AI verification when deterministic verification
is insufficient.
"""

VERIFICATION_SYSTEM_PROMPT = """You are the Verification Agent for RepoLens.

Your job is to evaluate a claim against provided evidence.

CRITICAL RULES:
1. Do NOT invent information not present in the evidence.
2. Do NOT assume the existence of files or code not shown.
3. If evidence is insufficient, return UNCERTAIN.
4. Evaluate ONLY the supplied evidence.
5. Be precise and factual.

OUTPUT SCHEMA (JSON):
{
  "truth_value": "TRUE|LIKELY_TRUE|UNCERTAIN|LIKELY_FALSE|FALSE",
  "confidence": 0-100,
  "reasoning": "explanation of your conclusion",
  "evidence_used": ["list of evidence items you relied on"]
}"""


def build_verification_prompt(
    claim_statement: str,
    claim_type: str,
    evidence_items: list[dict],
    relevant_files: list[str],
) -> str:
    """Build the user prompt for the AI Verification Agent."""

    prompt_parts = []

    prompt_parts.append("=== CLAIM TO VERIFY ===\n")
    prompt_parts.append(f"Type: {claim_type}\n")
    prompt_parts.append(f"Statement: {claim_statement}\n")

    prompt_parts.append("\n=== EVIDENCE ===")
    for i, ev in enumerate(evidence_items, 1):
        prompt_parts.append(
            f"\nEvidence {i} (relation: {ev.get('relation', 'unknown')}):"
        )
        prompt_parts.append(f"  Source: {ev.get('source', 'unknown')}")
        prompt_parts.append(f"  File: {ev.get('file_path', 'N/A')}")
        prompt_parts.append(f"  Content: {ev.get('content', 'N/A')[:300]}")

    if relevant_files:
        prompt_parts.append("\n\n=== RELEVANT FILE CONTENTS ===")
        for file_info in relevant_files:
            if isinstance(file_info, dict):
                prompt_parts.append(f"\n--- {file_info.get('path', 'unknown')} ---")
                prompt_parts.append(file_info.get("content", "")[:2000])
            else:
                prompt_parts.append(f"\n--- {file_info} ---")

    prompt_parts.append(
        "\n\n=== INSTRUCTIONS ===\n"
        "Evaluate the claim based ONLY on the provided evidence. "
        "Return your evaluation as JSON."
    )

    return "\n".join(prompt_parts)
