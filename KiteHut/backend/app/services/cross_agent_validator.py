"""
Cross-Agent Validation.

Detects relationships between findings from different agents.
Phase 3, Step 18.
"""

import re
from typing import List, Dict

from app.models.claim import Claim
from app.models.evidence import Evidence, NEUTRAL


def _generate_evidence_id(index: int) -> str:
    """Generate a unique evidence ID."""
    return f"ev_xa_{index:04d}"


# ============================================================
# Claim similarity detection
# ============================================================

def _normalize_text(text: str) -> str:
    """Normalize text for comparison."""
    text = text.lower()
    text = re.sub(r'[^\w\s]', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def _extract_keywords(text: str) -> set:
    """Extract meaningful keywords from text."""
    stop_words = {
        "the", "a", "an", "is", "are", "was", "were", "be", "been",
        "being", "have", "has", "had", "do", "does", "did", "will",
        "would", "could", "should", "may", "might", "can", "shall",
        "that", "this", "these", "those", "it", "its", "to", "of",
        "in", "for", "on", "with", "at", "by", "from", "as", "into",
        "no", "not", "or", "and", "but", "if", "then", "else",
    }
    words = set(_normalize_text(text).split())
    return words - stop_words


def _compute_similarity(text1: str, text2: str) -> float:
    """
    Compute keyword-based similarity between two texts.
    Returns a score between 0 and 1.
    """
    kw1 = _extract_keywords(text1)
    kw2 = _extract_keywords(text2)

    if not kw1 or not kw2:
        return 0.0

    intersection = kw1 & kw2
    union = kw1 | kw2

    return len(intersection) / len(union) if union else 0.0


# ============================================================
# Cross-agent relationship detection
# ============================================================

def _detect_relationship(claim_a: Claim, claim_b: Claim) -> str | None:
    """
    Detect the relationship between two claims from different agents.

    Returns: "supports", "contradicts", "related", "duplicate", or None
    """
    if claim_a.source_agent == claim_b.source_agent:
        return None

    similarity = _compute_similarity(claim_a.statement, claim_b.statement)

    # High similarity = duplicate
    if similarity > 0.6:
        return "duplicate"

    # Medium similarity = related
    if similarity > 0.3:
        # Check for contradiction patterns
        negation_patterns = [
            (r"\bno\b", r"\bhas\b"),
            (r"\bmissing\b", r"\bpresent\b"),
            (r"\blacks?\b", r"\bhas\b"),
            (r"\babsent\b", r"\bexists\b"),
        ]

        a_text = claim_a.statement.lower()
        b_text = claim_b.statement.lower()

        for neg_pat, pos_pat in negation_patterns:
            a_neg = bool(re.search(neg_pat, a_text))
            b_pos = bool(re.search(pos_pat, b_text))
            a_pos = bool(re.search(pos_pat, a_text))
            b_neg = bool(re.search(neg_pat, b_text))

            if (a_neg and b_pos) or (a_pos and b_neg):
                return "contradicts"

        return "related"

    # Same claim type from different agents = supports
    if (claim_a.claim_type == claim_b.claim_type
            and claim_a.category == claim_b.category):
        return "supports"

    return None


def validate_cross_agent(
    claims: List[Claim],
    evidence: List[Evidence],
    evidence_id_start: int = 1,
) -> List[Evidence]:
    """
    Validate claims across agents and generate cross-agent evidence.

    Returns additional evidence items showing cross-agent relationships.
    """
    cross_evidence = []
    evidence_index = evidence_id_start

    # Group claims by category
    category_claims: Dict[str, List[Claim]] = {}
    for claim in claims:
        cat = claim.category
        if cat not in category_claims:
            category_claims[cat] = []
        category_claims[cat].append(claim)

    # Check cross-agent relationships within same category
    for category, cat_claims in category_claims.items():
        for i in range(len(cat_claims)):
            for j in range(i + 1, len(cat_claims)):
                claim_a = cat_claims[i]
                claim_b = cat_claims[j]

                relationship = _detect_relationship(claim_a, claim_b)

                if relationship is None:
                    continue

                # Create cross-agent evidence
                if relationship == "supports":
                    ev = Evidence(
                        evidence_id=_generate_evidence_id(evidence_index),
                        claim_id=claim_a.claim_id,
                        source="cross_agent_validation",
                        type="structural",
                        file_path="",
                        line_start=0,
                        line_end=0,
                        content=(
                            f"Agent '{claim_b.source_agent}' independently "
                            f"identified a related issue: {claim_b.statement[:200]}"
                        ),
                        relation="supports",
                        strength="medium",
                    )
                    cross_evidence.append(ev)
                    evidence_index += 1

                elif relationship == "contradicts":
                    ev = Evidence(
                        evidence_id=_generate_evidence_id(evidence_index),
                        claim_id=claim_a.claim_id,
                        source="cross_agent_validation",
                        type="structural",
                        file_path="",
                        line_start=0,
                        line_end=0,
                        content=(
                            f"Agent '{claim_b.source_agent}' found "
                            f"contradicting information: {claim_b.statement[:200]}"
                        ),
                        relation="contradicts",
                        strength="medium",
                    )
                    cross_evidence.append(ev)
                    evidence_index += 1

                elif relationship == "duplicate":
                    ev = Evidence(
                        evidence_id=_generate_evidence_id(evidence_index),
                        claim_id=claim_a.claim_id,
                        source="cross_agent_validation",
                        type="structural",
                        file_path="",
                        line_start=0,
                        line_end=0,
                        content=(
                            f"Duplicate finding from agent '{claim_b.source_agent}': "
                            f"{claim_b.statement[:200]}"
                        ),
                        relation="supports",
                        strength="weak",
                    )
                    cross_evidence.append(ev)
                    evidence_index += 1

    print(f"  [CrossAgentValidator] Found {len(cross_evidence)} cross-agent relationships.")

    return cross_evidence
