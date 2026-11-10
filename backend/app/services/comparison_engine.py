"""
Comparison Engine.

Compares findings between two analysis runs to detect:
- NEW findings (present in current, not in previous)
- RESOLVED findings (present in previous, not in current)
- EXISTING findings (same fingerprint, same values)
- CHANGED findings (same fingerprint, different priority/score)

Phase 5, Step 25.
"""

from sqlalchemy.orm import Session

from app.db_models.analysis_run import AnalysisRun
from app.db_models.finding import Finding
from app.models.api_responses import (
    ComparisonResult,
    ComparisonSummary,
    FindingSummary,
)


def compare_analyses(
    db: Session,
    previous_run_id: int,
    current_run_id: int,
) -> ComparisonResult:
    """
    Compare two analysis runs and classify findings.

    Returns a ComparisonResult with new, resolved, existing, and changed findings.
    """
    # Get both runs
    previous_run = db.query(AnalysisRun).filter(AnalysisRun.id == previous_run_id).first()
    current_run = db.query(AnalysisRun).filter(AnalysisRun.id == current_run_id).first()

    if not previous_run:
        raise ValueError(f"Previous analysis run {previous_run_id} not found")
    if not current_run:
        raise ValueError(f"Current analysis run {current_run_id} not found")

    # Get findings for both runs
    previous_findings = db.query(Finding).filter(
        Finding.analysis_run_id == previous_run_id
    ).all()
    current_findings = db.query(Finding).filter(
        Finding.analysis_run_id == current_run_id
    ).all()

    # Build fingerprint maps
    prev_map = {f.fingerprint: f for f in previous_findings}
    curr_map = {f.fingerprint: f for f in current_findings}

    # Classify findings
    new_findings = []
    resolved_findings = []
    existing_findings = []
    changed_findings = []

    # Check current findings
    for fp, curr_f in curr_map.items():
        if fp in prev_map:
            prev_f = prev_map[fp]
            # Same fingerprint - check if values changed
            if _has_changed(prev_f, curr_f):
                changed_findings.append({
                    "fingerprint": fp,
                    "previous": _finding_to_summary(prev_f),
                    "current": _finding_to_summary(curr_f),
                    "changes": _detect_changes(prev_f, curr_f),
                })
            else:
                existing_findings.append(_finding_to_summary(curr_f))
        else:
            # New finding
            new_findings.append(_finding_to_summary(curr_f))

    # Check for resolved findings
    for fp, prev_f in prev_map.items():
        if fp not in curr_map:
            resolved_findings.append(_finding_to_summary(prev_f))

    summary = ComparisonSummary(
        new=len(new_findings),
        resolved=len(resolved_findings),
        existing=len(existing_findings),
        changed=len(changed_findings),
    )

    return ComparisonResult(
        repository_id=current_run.repository_id,
        previous_analysis_id=previous_run_id,
        current_analysis_id=current_run_id,
        summary=summary,
        new_findings=new_findings,
        resolved_findings=resolved_findings,
        existing_findings=existing_findings,
        changed_findings=changed_findings,
    )


def get_previous_run(
    db: Session,
    repository_id: int,
    current_run_id: int,
) -> AnalysisRun | None:
    """Find the most recent completed analysis run before the current one."""
    return db.query(AnalysisRun).filter(
        AnalysisRun.repository_id == repository_id,
        AnalysisRun.id < current_run_id,
        AnalysisRun.status == "COMPLETED",
    ).order_by(AnalysisRun.created_at.desc()).first()


def _has_changed(prev: Finding, curr: Finding) -> bool:
    """Check if a finding has changed between runs."""
    return (
        prev.priority != curr.priority
        or abs(prev.final_score - curr.final_score) > 1.0
        or prev.truth_value != curr.truth_value
    )


def _detect_changes(prev: Finding, curr: Finding) -> list[str]:
    """Detect what changed between two findings with the same fingerprint."""
    changes = []
    if prev.priority != curr.priority:
        changes.append(f"Priority: {prev.priority} -> {curr.priority}")
    if abs(prev.final_score - curr.final_score) > 1.0:
        changes.append(f"Score: {prev.final_score:.0f} -> {curr.final_score:.0f}")
    if prev.truth_value != curr.truth_value:
        changes.append(f"Truth: {prev.truth_value} -> {curr.truth_value}")
    if abs(prev.confidence - curr.confidence) > 5.0:
        changes.append(f"Confidence: {prev.confidence:.0f} -> {curr.confidence:.0f}")
    return changes


def _finding_to_summary(f: Finding) -> FindingSummary:
    """Convert a Finding DB model to a FindingSummary."""
    return FindingSummary(
        id=f.id,
        fingerprint=f.fingerprint,
        claim_type=f.claim_type,
        category=f.category,
        statement=f.statement,
        source_agent=f.source_agent,
        truth_value=f.truth_value,
        confidence=f.confidence,
        severity=f.severity,
        severity_score=f.severity_score,
        final_score=f.final_score,
        priority=f.priority,
    )
