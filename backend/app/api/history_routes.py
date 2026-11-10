"""
History API Routes.

Endpoints for analysis history, repository details, and finding details.
Phase 5, Step 24.
"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.db_models.repository import Repository
from app.db_models.analysis_run import AnalysisRun
from app.db_models.finding import Finding
from app.db_models.evidence import Evidence
from app.models.api_responses import (
    RepositoryResponse,
    RepositoryListResponse,
    AnalysisRunResponse,
    AnalysisListResponse,
    AnalysisDetail,
    FindingSummary,
    FindingDetail,
    FindingListResponse,
    EvidenceResponse,
    ComparisonResult,
)

router = APIRouter(prefix="/api/v1", tags=["History"])


# ============================================================
# Repository Endpoints
# ============================================================

@router.get("/repositories", response_model=RepositoryListResponse)
def list_repositories(db: Session = Depends(get_db)):
    """List all analyzed repositories."""
    repos = db.query(Repository).order_by(Repository.last_analyzed_at.desc()).all()

    result = []
    for repo in repos:
        analysis_count = db.query(AnalysisRun).filter(
            AnalysisRun.repository_id == repo.id
        ).count()
        result.append(RepositoryResponse(
            id=repo.id,
            github_url=repo.github_url,
            owner=repo.owner,
            name=repo.name,
            default_branch=repo.default_branch,
            first_analyzed_at=repo.first_analyzed_at,
            last_analyzed_at=repo.last_analyzed_at,
            analysis_count=analysis_count,
        ))

    return RepositoryListResponse(repositories=result)


@router.get("/repositories/{repository_id}", response_model=RepositoryResponse)
def get_repository(repository_id: int, db: Session = Depends(get_db)):
    """Get repository details."""
    repo = db.query(Repository).filter(Repository.id == repository_id).first()
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")

    analysis_count = db.query(AnalysisRun).filter(
        AnalysisRun.repository_id == repo.id
    ).count()

    return RepositoryResponse(
        id=repo.id,
        github_url=repo.github_url,
        owner=repo.owner,
        name=repo.name,
        default_branch=repo.default_branch,
        first_analyzed_at=repo.first_analyzed_at,
        last_analyzed_at=repo.last_analyzed_at,
        analysis_count=analysis_count,
    )


@router.get("/repositories/{repository_id}/analyses", response_model=AnalysisListResponse)
def list_repository_analyses(repository_id: int, db: Session = Depends(get_db)):
    """List all analysis runs for a repository."""
    repo = db.query(Repository).filter(Repository.id == repository_id).first()
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")

    runs = db.query(AnalysisRun).filter(
        AnalysisRun.repository_id == repository_id
    ).order_by(AnalysisRun.created_at.desc()).all()

    return AnalysisListResponse(analyses=[
        AnalysisRunResponse(
            id=run.id,
            repository_id=run.repository_id,
            status=run.status,
            branch=run.branch,
            commit_hash=run.commit_hash,
            started_at=run.started_at,
            completed_at=run.completed_at,
            duration_seconds=run.duration_seconds,
            total_findings=run.total_findings,
            error_message=run.error_message,
            created_at=run.created_at,
            mode=run.mode,
            enabled_agents=_decode_agents(run.enabled_agents),
        )
        for run in runs
    ])


def _decode_agents(raw: str | None) -> list[str] | None:
    """Decode the JSON-encoded enabled_agents column."""
    if not raw:
        return None
    import json
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        return None


# ============================================================
# Analysis Endpoints
# ============================================================

@router.get("/analyses/{analysis_id}", response_model=AnalysisDetail)
def get_analysis(analysis_id: int, db: Session = Depends(get_db)):
    """Get analysis details with priority distribution."""
    run = db.query(AnalysisRun).filter(AnalysisRun.id == analysis_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Analysis not found")

    # Calculate priority distribution
    findings = db.query(Finding).filter(Finding.analysis_run_id == run.id).all()
    priority_dist = {}
    for f in findings:
        priority_dist[f.priority] = priority_dist.get(f.priority, 0) + 1

    return AnalysisDetail(
        id=run.id,
        repository_id=run.repository_id,
        status=run.status,
        branch=run.branch,
        commit_hash=run.commit_hash,
        started_at=run.started_at,
        completed_at=run.completed_at,
        duration_seconds=run.duration_seconds,
        total_findings=run.total_findings,
        error_message=run.error_message,
        created_at=run.created_at,
        priority_distribution=priority_dist,
    )


@router.get("/analyses/{analysis_id}/findings", response_model=FindingListResponse)
def list_analysis_findings(
    analysis_id: int,
    priority: Optional[str] = Query(None, description="Filter by priority (P0, P1, etc.)"),
    severity: Optional[str] = Query(None, description="Filter by severity (CRITICAL, HIGH, etc.)"),
    truth_value: Optional[str] = Query(None, description="Filter by truth value"),
    category: Optional[str] = Query(None, description="Filter by category"),
    status: Optional[str] = Query(None, description="Filter by status (OPEN, RESOLVED, ...)"),
    db: Session = Depends(get_db),
):
    """List findings for an analysis run with optional filters."""
    run = db.query(AnalysisRun).filter(AnalysisRun.id == analysis_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Analysis not found")

    query = db.query(Finding).filter(Finding.analysis_run_id == analysis_id)

    if priority:
        query = query.filter(Finding.priority == priority)
    if severity:
        query = query.filter(Finding.severity == severity)
    if truth_value:
        query = query.filter(Finding.truth_value == truth_value)
    if category:
        query = query.filter(Finding.category == category)
    if status:
        query = query.filter(Finding.status == status.upper())

    findings = query.order_by(Finding.final_score.desc()).all()

    return FindingListResponse(
        findings=[
            FindingSummary(
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
                status=f.status,
                status_note=f.status_note,
            )
            for f in findings
        ],
        total=len(findings),
    )


# ============================================================
# Comparison Endpoint
# ============================================================

@router.get("/analyses/{analysis_id}/compare", response_model=ComparisonResult)
def compare_with_previous(
    analysis_id: int,
    previous_analysis_id: Optional[int] = Query(None, description="Previous analysis ID to compare with"),
    db: Session = Depends(get_db),
):
    """Compare an analysis run with its previous (or a specific) run."""
    from app.services.comparison_engine import compare_analyses, get_previous_run

    current_run = db.query(AnalysisRun).filter(AnalysisRun.id == analysis_id).first()
    if not current_run:
        raise HTTPException(status_code=404, detail="Analysis not found")

    # Find previous run
    if previous_analysis_id:
        prev_id = previous_analysis_id
    else:
        prev_run = get_previous_run(db, current_run.repository_id, analysis_id)
        if not prev_run:
            raise HTTPException(
                status_code=404,
                detail="No previous analysis found for comparison"
            )
        prev_id = prev_run.id

    try:
        result = compare_analyses(db, prev_id, analysis_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ============================================================
# Finding Endpoints
# ============================================================

@router.get("/findings/{finding_id}", response_model=FindingDetail)
def get_finding(finding_id: int, db: Session = Depends(get_db)):
    """Get full finding detail with evidence."""
    finding = db.query(Finding).filter(Finding.id == finding_id).first()
    if not finding:
        raise HTTPException(status_code=404, detail="Finding not found")

    evidence_items = db.query(Evidence).filter(
        Evidence.finding_id == finding.id
    ).all()

    return FindingDetail(
        id=finding.id,
        fingerprint=finding.fingerprint,
        claim_type=finding.claim_type,
        category=finding.category,
        statement=finding.statement,
        source_agent=finding.source_agent,
        truth_value=finding.truth_value,
        confidence=finding.confidence,
        severity=finding.severity,
        severity_score=finding.severity_score,
        user_impact=finding.user_impact,
        system_impact=finding.system_impact,
        business_impact=finding.business_impact,
        overall_impact=finding.overall_impact,
        exploitability=finding.exploitability,
        final_score=finding.final_score,
        priority=finding.priority,
        status=finding.status,
        status_note=finding.status_note,
        status_updated_at=finding.status_updated_at,
        evidence=[
            EvidenceResponse(
                id=ev.id,
                evidence_type=ev.evidence_type,
                source=ev.source,
                file_path=ev.file_path,
                line_start=ev.line_start,
                line_end=ev.line_end,
                content=ev.content,
                relation=ev.relation,
                strength=ev.strength,
            )
            for ev in evidence_items
        ],
    )
