"""
Root Cause Analysis Engine.

Groups related findings under common root causes.
Detects patterns like:
- Multiple security issues from missing auth layer
- Quality issues from large functions
- Testing gaps across components
"""

from typing import List
from collections import defaultdict

from app.models.scored_finding import ScoredFinding
from app.models.root_cause import RootCauseGroup


# Root cause patterns: claim_types -> (root_cause_description, category)
ROOT_CAUSE_PATTERNS = {
    "missing_security_layer": {
        "types": {"missing_authentication", "missing_authorization", "weak_input_validation"},
        "cause": "Missing or incomplete security layer",
        "category": "security",
        "description": "Multiple security controls are absent, suggesting a missing security implementation layer.",
        "fix": "Implement a comprehensive security layer with authentication, authorization, and input validation.",
    },
    "hardcoded_secrets": {
        "types": {"hardcoded_secret", "insecure_configuration", "debug_mode_enabled"},
        "cause": "Insecure configuration management",
        "category": "security",
        "description": "Secrets and sensitive configuration are hardcoded instead of using environment variables.",
        "fix": "Move all secrets to environment variables and use a secrets manager.",
    },
    "code_quality_debt": {
        "types": {"large_function", "large_class", "code_duplication"},
        "cause": "Accumulated code quality debt",
        "category": "quality",
        "description": "Code has grown complex with duplicated logic and oversized functions/classes.",
        "fix": "Refactor large functions, extract classes, and eliminate code duplication.",
    },
    "testing_gap": {
        "types": {"missing_tests", "low_test_coverage", "missing_integration_tests", "missing_test_framework"},
        "cause": "Insufficient test coverage",
        "category": "testing",
        "description": "Lack of tests increases risk of regressions and makes changes harder to validate.",
        "fix": "Add test framework, write unit tests for critical paths, add integration tests.",
    },
    "architecture_issues": {
        "types": {"tight_coupling", "layer_violation", "missing_separation", "circular_dependency"},
        "cause": "Architectural boundary violations",
        "category": "architecture",
        "description": "Code violates layer boundaries or has tight coupling between components.",
        "fix": "Enforce layer boundaries, use dependency injection, break circular dependencies.",
    },
}


def analyze_root_causes(
    scored_findings: List[ScoredFinding],
) -> List[RootCauseGroup]:
    """
    Analyze scored findings and group them by root cause.
    """
    # Group findings by claim type
    type_findings: dict[str, list[ScoredFinding]] = defaultdict(list)
    for f in scored_findings:
        type_findings[f.claim_type].append(f)

    groups = []
    matched_types = set()

    # Check each root cause pattern
    for group_name, pattern in ROOT_CAUSE_PATTERNS.items():
        matching = []
        for ct in pattern["types"]:
            if ct in type_findings:
                matching.extend(type_findings[ct])
                matched_types.add(ct)

        if len(matching) >= 2:  # Need at least 2 related findings
            priorities = [f.priority for f in matching]
            highest_priority = min(priorities)  # P0 < P1 < P2

            group = RootCauseGroup(
                group_id=f"rc_{group_name}",
                root_cause=pattern["cause"],
                category=pattern["category"],
                finding_ids=[f.finding_id for f in matching],
                finding_count=len(matching),
                severity=_highest_severity(matching),
                priority=highest_priority,
                description=pattern["description"],
                fix_suggestion=pattern["fix"],
            )
            groups.append(group)

    # Handle unmatched findings as individual root causes
    for ct, findings in type_findings.items():
        if ct not in matched_types and findings:
            group = RootCauseGroup(
                group_id=f"rc_individual_{ct}",
                root_cause=f"Issue: {ct.replace('_', ' ').title()}",
                category=_infer_category(ct),
                finding_ids=[f.finding_id for f in findings],
                finding_count=len(findings),
                severity=_highest_severity(findings),
                priority=min(f.priority for f in findings),
                description=f"Individual finding type: {ct.replace('_', ' ')}",
                fix_suggestion=f"Address {ct.replace('_', ' ')} issues.",
            )
            groups.append(group)

    # Sort by priority
    groups.sort(key=lambda g: g.priority)

    print(f"  [RootCauseEngine] Identified {len(groups)} root cause groups.")

    return groups


def _highest_severity(findings: List[ScoredFinding]) -> str:
    """Get the highest severity level from a list of findings."""
    severity_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "INFO": 4}
    best = "INFO"
    for f in findings:
        if severity_order.get(f.severity.level, 4) < severity_order.get(best, 4):
            best = f.severity.level
    return best


def _infer_category(claim_type: str) -> str:
    """Infer category from claim type."""
    from app.models.claim import CLAIM_CATEGORIES
    for category, types in CLAIM_CATEGORIES.items():
        if claim_type in types:
            return category
    return "unknown"
