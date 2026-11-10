"""
Evidence Normalization.

Normalizes evidence from different collection sources into a consistent format.
Phase 3, Step 16.
"""

from typing import List

from app.models.evidence import (
    Evidence,
    SUPPORTS,
    CONTRADICTS,
    NEUTRAL,
    STRONG,
    MEDIUM,
    WEAK,
)


# Source priority for evidence strength adjustment
SOURCE_STRENGTH = {
    "file_scan": STRONG,       # Direct file content scan
    "file_presence": MEDIUM,   # File existence check
    "structure_scan": STRONG,  # Structural analysis
    "pattern_scan": MEDIUM,    # Pattern matching
    "dependency_scan": MEDIUM, # Dependency analysis
    "keyword_search": WEAK,    # Generic keyword search
    "scanner": STRONG,         # Scanner results
}


def normalize_evidence(evidence: Evidence) -> Evidence:
    """
    Normalize a single evidence item.

    Ensures consistent formatting and adjusts strength
    based on source reliability.
    """
    # Normalize relation
    relation_lower = evidence.relation.lower()
    if relation_lower not in {SUPPORTS, CONTRADICTS, NEUTRAL}:
        # Try to map common variations
        if "support" in relation_lower or "confirm" in relation_lower:
            evidence.relation = SUPPORTS
        elif "contradict" in relation_lower or "refute" in relation_lower:
            evidence.relation = CONTRADICTS
        else:
            evidence.relation = NEUTRAL

    # Normalize strength
    strength_lower = evidence.strength.lower()
    if strength_lower not in {STRONG, MEDIUM, WEAK}:
        evidence.strength = MEDIUM

    # Adjust strength based on source reliability
    source_expected = SOURCE_STRENGTH.get(evidence.source)
    if source_expected:
        # Don't downgrade strong evidence from reliable sources
        if evidence.strength == WEAK and source_expected in {STRONG, MEDIUM}:
            evidence.strength = MEDIUM

    # Clean up content
    evidence.content = evidence.content.strip()
    if len(evidence.content) > 500:
        evidence.content = evidence.content[:500] + "..."

    # Normalize file path
    evidence.file_path = evidence.file_path.strip()
    if evidence.file_path.startswith("/"):
        evidence.file_path = evidence.file_path[1:]

    return evidence


def normalize_evidence_list(evidence_list: List[Evidence]) -> List[Evidence]:
    """
    Normalize a list of evidence items.
    """
    normalized = []
    for evidence in evidence_list:
        normalized.append(normalize_evidence(evidence))

    print(f"  [EvidenceNormalizer] Normalized {len(normalized)} evidence items.")

    return normalized


def deduplicate_evidence(evidence_list: List[Evidence]) -> List[Evidence]:
    """
    Remove duplicate evidence items.

    Deduplicates based on file_path + line_start + content.
    Keeps the evidence with stronger relation (supports > neutral > contradicts).
    """
    seen = {}
    result = []

    relation_priority = {SUPPORTS: 3, NEUTRAL: 2, CONTRADICTS: 1}

    for evidence in evidence_list:
        key = (evidence.file_path, evidence.line_start, evidence.content[:100])

        if key in seen:
            existing = seen[key]
            # Keep the one with stronger relation
            if relation_priority.get(evidence.relation, 0) > relation_priority.get(existing.relation, 0):
                result.remove(existing)
                seen[key] = evidence
                result.append(evidence)
        else:
            seen[key] = evidence
            result.append(evidence)

    if len(evidence_list) != len(result):
        print(f"  [EvidenceNormalizer] Deduplicated: {len(evidence_list)} -> {len(result)} items.")

    return result
