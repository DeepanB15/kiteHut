"""
Quality Gate Engine (Phase 9).

Evaluates a pull request analysis against configurable thresholds and
produces a PASS/FAIL verdict plus human-readable reasons. The verdict
drives the GitHub commit status check posted on the PR's head commit.

Rules (all configurable via settings):
    - critical (P0) findings > QUALITY_GATE_CRITICAL_LIMIT  -> FAIL
    - security findings      > QUALITY_GATE_SECURITY_LIMIT  -> FAIL
    - health score           < QUALITY_GATE_MIN_HEALTH      -> FAIL (when provided)
    - otherwise                                              -> PASS

A PR scan only inspects *new* code, so any security finding in a PR
analysis counts as a new security issue introduced by the pull request.
"""

from dataclasses import dataclass, field

from app.core.config import settings

# Categories the PR scanner reports that are security-related.
_SECURITY_CATEGORIES = {
    "hardcoded_secret",
    "private_key",
    "hardcoded_password",
    "insecure_tls",
    "shell_injection",
    "sql_injection",
    "dangerous_eval",
}


@dataclass
class QualityGateResult:
    """Outcome of evaluating the quality gate for one analysis."""

    result: str  # "PASS" | "FAIL"
    reasons: list[str] = field(default_factory=list)
    counts: dict[str, float | int | None] = field(default_factory=dict)
    summary: str = ""

    @property
    def passed(self) -> bool:
        return self.result == "PASS"


def evaluate_quality_gate(
    findings: list,
    health_score: float | None = None,
    limits: dict | None = None,
) -> QualityGateResult:
    """
    Evaluate the quality gate for a set of findings.

    `findings` may be any objects exposing `.category` and `.severity`
    (e.g. ScanFinding from the PR scanner).

    Args:
        findings: findings detected in the analyzed code.
        health_score: optional repository health score (0-100). PR
            analyses do not compute one; repository analyses can pass it.
        limits: optional per-repository overrides for the thresholds
            (keys: critical_limit, security_limit, min_health). Falls
            back to global settings when absent.

    Returns:
        QualityGateResult with PASS/FAIL, reasons, and counts.
    """
    limits = limits or {}
    critical_limit = limits.get(
        "critical_limit", settings.QUALITY_GATE_CRITICAL_LIMIT
    )
    security_limit = limits.get(
        "security_limit", settings.QUALITY_GATE_SECURITY_LIMIT
    )
    min_health = limits.get(
        "min_health", settings.QUALITY_GATE_MIN_HEALTH
    )

    findings = list(findings or [])
    critical = [
        f for f in findings
        if getattr(f, "severity", "").upper() == "CRITICAL"
    ]
    security = [
        f for f in findings
        if getattr(f, "category", "") in _SECURITY_CATEGORIES
    ]

    reasons: list[str] = []
    if len(critical) > critical_limit:
        reasons.append(
            f"{len(critical)} critical finding(s) — above limit "
            f"{critical_limit}"
        )
    if len(security) > security_limit:
        reasons.append(
            f"{len(security)} security finding(s) — above limit "
            f"{security_limit}"
        )
    if health_score is not None and health_score < min_health:
        reasons.append(
            f"Health score {health_score:.0f} — below minimum "
            f"{min_health:.0f}"
        )

    result = "PASS" if not reasons else "FAIL"
    summary = (
        "No critical or security issues found."
        if result == "PASS"
        else "; ".join(reasons)
    )

    return QualityGateResult(
        result=result,
        reasons=reasons,
        counts={
            "critical": len(critical),
            "security": len(security),
            "health": health_score,
        },
        summary=summary,
    )


def status_check_description(gate: QualityGateResult) -> str:
    """Short description for the GitHub commit status check (<= 140 chars)."""
    if gate.result == "PASS":
        return f"RepoLens: {gate.summary}"
    counts = gate.counts
    parts = []
    if counts.get("critical"):
        parts.append(f"{counts['critical']} critical")
    if counts.get("security"):
        parts.append(f"{counts['security']} security")
    suffix = ", ".join(parts) or "issues found"
    return f"RepoLens: {suffix} — {gate.summary[:80]}"