"""
GitHub Integration API Routes (Phase 9).

Endpoints:
    POST /api/v1/analyze-pr                 queue a pull request analysis
    POST /api/v1/webhooks/github            GitHub webhook receiver
    GET  /api/v1/github/status              connection status
    GET  /api/v1/pr-analyses                list PR analyses
    GET  /api/v1/pr-analyses/{id}           PR analysis detail with findings
    GET  /api/v1/repositories/{id}/pr-analyses
    GET  /api/v1/repositories/{id}/health-trend
"""

import hashlib
import hmac
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.db_models.pr_analysis import PrAnalysis
from app.db_models.repository_health import RepositoryHealth
from app.models.analysis import AnalysisJobResponse
from app.models.pr_analysis import (
    GithubStatusResponse,
    PrAnalysisDetail,
    PrAnalysisListResponse,
    PrAnalysisRequest,
    PrAnalysisSummary,
    PrFindingResponse,
    HealthTrendResponse,
    HealthTrendPoint,
)
from app.services.github_client import GitHubClient
from app.services.git_service import InvalidRepositoryURL, validate_github_repository_url
from app.services.job_service import create_job, start_analysis_job

logger = logging.getLogger("repolens.github_routes")

router = APIRouter(prefix="/api/v1", tags=["GitHub Integration"])

# pull_request actions that should trigger an analysis
_PR_ANALYZE_ACTIONS = {"opened", "synchronize", "reopened"}


# ============================================================
# Analyze a pull request (manual / GitHub Actions trigger)
# ============================================================

@router.post(
    "/analyze-pr",
    response_model=AnalysisJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def analyze_pull_request(request: PrAnalysisRequest):
    """Queue a pull request analysis and return a job id (202)."""
    repository_url = str(request.repository_url)

    try:
        validate_github_repository_url(repository_url)
    except InvalidRepositoryURL as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        )

    job = create_job(
        repository_url,
        job_type="PR",
        pull_number=request.pull_number,
    )
    start_analysis_job(
        job.job_id,
        repository_url,
        job_type="PR",
        pull_number=request.pull_number,
    )

    return AnalysisJobResponse(
        job_id=job.job_id,
        repository_url=repository_url,
        job_type="PR",
        pull_number=request.pull_number,
        status=job.status,
        created_at=job.created_at,
    )


# ============================================================
# GitHub webhook receiver
# ============================================================

@router.post("/webhooks/github")
async def github_webhook(request: Request):
    """
    Receive GitHub webhooks.

    Supported events:
        push            -> queue a full repository analysis
        pull_request    -> queue a PR analysis (opened/synchronize/reopened)
        ping            -> respond OK (used during webhook setup)

    Requires GITHUB_WEBHOOK_SECRET to be configured; the request must
    carry a valid X-Hub-Signature-256.
    """
    secret = settings.GITHUB_WEBHOOK_SECRET
    if not secret:
        raise HTTPException(
            status_code=503,
            detail="GitHub webhooks are not configured. "
                   "Set GITHUB_WEBHOOK_SECRET in the environment.",
        )

    body = await request.body()

    # Verify the HMAC signature
    signature = request.headers.get("x-hub-signature-256", "")
    expected = "sha256=" + hmac.new(
        secret.encode("utf-8"), body, hashlib.sha256
    ).hexdigest()
    if not signature or not hmac.compare_digest(signature, expected):
        raise HTTPException(
            status_code=401,
            detail="Invalid webhook signature",
        )

    event = request.headers.get("x-github-event", "")
    delivery = request.headers.get("x-github-delivery", "unknown")
    logger.info("Received GitHub webhook: event=%s delivery=%s", event, delivery)

    try:
        payload = await request.json()
    except Exception:
        payload = {}

    if event == "ping":
        return {"status": "pong"}

    if event == "push":
        return _queue_from_push(payload)

    if event == "pull_request":
        return _queue_from_pull_request(payload)

    logger.info("Ignoring unsupported webhook event: %s", event)
    return {"status": "ignored", "event": event}


def _queue_from_push(payload: dict) -> dict:
    """Queue a repository analysis on push to the default branch."""
    repo = payload.get("repository") or {}
    clone_url = repo.get("clone_url") or repo.get("html_url")
    ref = payload.get("ref", "")

    if not clone_url:
        raise HTTPException(status_code=422, detail="Missing repository in payload")

    try:
        validate_github_repository_url(clone_url)
    except InvalidRepositoryURL as error:
        raise HTTPException(status_code=422, detail=str(error))

    job = create_job(clone_url, job_type="REPOSITORY")
    start_analysis_job(job.job_id, clone_url, job_type="REPOSITORY")
    logger.info("Push webhook queued repository job %s (ref=%s)", job.job_id, ref)
    return {"status": "queued", "job_id": job.job_id, "kind": "repository"}


def _queue_from_pull_request(payload: dict) -> dict:
    """Queue a PR analysis when the PR is opened / updated."""
    action = payload.get("action", "")
    if action not in _PR_ANALYZE_ACTIONS:
        return {"status": "ignored", "reason": f"action={action}"}

    pr = payload.get("pull_request") or {}
    repo = payload.get("repository") or {}
    clone_url = repo.get("clone_url") or repo.get("html_url")
    number = pr.get("number")

    if not clone_url or not number:
        raise HTTPException(status_code=422, detail="Incomplete pull_request payload")

    try:
        validate_github_repository_url(clone_url)
    except InvalidRepositoryURL as error:
        raise HTTPException(status_code=422, detail=str(error))

    job = create_job(
        clone_url, job_type="PR", pull_number=int(number)
    )
    start_analysis_job(
        job.job_id,
        clone_url,
        job_type="PR",
        pull_number=int(number),
    )
    logger.info("PR webhook queued PR job %s for #%s (action=%s)",
                job.job_id, number, action)
    return {"status": "queued", "job_id": job.job_id, "kind": "pull_request"}


# ============================================================
# GitHub connection status
# ============================================================

@router.get("/github/status", response_model=GithubStatusResponse)
def github_status():
    """Report GitHub connection configuration and token validity."""
    client = GitHubClient()
    try:
        user = client.get_authenticated_user()
        rate_limit = client.get_rate_limit() if client.token else None
        return GithubStatusResponse(
            authenticated=bool(user),
            username=(user or {}).get("login"),
            rate_limit=rate_limit,
            webhook_secret_configured=bool(settings.GITHUB_WEBHOOK_SECRET),
            pr_comments_enabled=settings.PR_POST_COMMENT,
            status_checks_enabled=settings.PR_POST_STATUS_CHECK,
            message=(
                "Connected as " + (user or {}).get("login", "")
                if user else
                "No GITHUB_TOKEN configured — public repositories only, "
                "PR comments disabled."
            ),
        )
    finally:
        client.close()


# ============================================================
# PR analysis history
# ============================================================

def _to_summary(record: PrAnalysis) -> PrAnalysisSummary:
    return PrAnalysisSummary(
        id=record.id,
        repository_id=record.repository_id,
        pull_number=record.pull_number,
        pr_title=record.pr_title,
        pr_url=record.pr_url,
        status=record.status,
        findings_count=record.findings_count,
        error_message=record.error_message,
        comment_posted=record.comment_posted,
        gate_result=record.gate_result,
        gate_reasons=(
            [r for r in record.gate_reasons.split("\n") if r]
            if record.gate_reasons else None
        ),
        status_check_posted=record.status_check_posted,
        created_at=record.created_at,
        completed_at=record.completed_at,
    )


@router.get("/pr-analyses", response_model=PrAnalysisListResponse)
def list_pr_analyses(
    repository_id: int | None = Query(None),
    pull_number: int | None = Query(None),
    db: Session = Depends(get_db),
):
    """List pull request analyses, newest first."""
    query = db.query(PrAnalysis)
    if repository_id is not None:
        query = query.filter(PrAnalysis.repository_id == repository_id)
    if pull_number is not None:
        query = query.filter(PrAnalysis.pull_number == pull_number)

    records = query.order_by(PrAnalysis.created_at.desc()).limit(100).all()
    return PrAnalysisListResponse(
        pr_analyses=[_to_summary(r) for r in records],
        total=len(records),
    )


@router.get("/pr-analyses/{pr_analysis_id}", response_model=PrAnalysisDetail)
def get_pr_analysis(pr_analysis_id: int, db: Session = Depends(get_db)):
    """Get a pull request analysis with its findings."""
    record = db.query(PrAnalysis).filter(
        PrAnalysis.id == pr_analysis_id
    ).first()
    if not record:
        raise HTTPException(status_code=404, detail="PR analysis not found")

    detail = PrAnalysisDetail(**_to_summary(record).model_dump())
    detail.base_sha = record.base_sha
    detail.head_sha = record.head_sha
    detail.findings = [
        PrFindingResponse(
            id=f.id,
            category=f.category,
            severity=f.severity,
            priority=f.priority,
            file_path=f.file_path,
            line_start=f.line_start,
            code_snippet=f.code_snippet,
            message=f.message,
            recommendation=f.recommendation,
            source=f.source,
            confidence=f.confidence,
            status=f.status,
            status_note=f.status_note,
        )
        for f in sorted(record.findings, key=lambda x: (x.id,))
    ]
    return detail


@router.get(
    "/repositories/{repository_id}/pr-analyses",
    response_model=PrAnalysisListResponse,
)
def list_repository_pr_analyses(
    repository_id: int,
    db: Session = Depends(get_db),
):
    """List PR analyses for a specific repository."""
    records = db.query(PrAnalysis).filter(
        PrAnalysis.repository_id == repository_id
    ).order_by(PrAnalysis.created_at.desc()).limit(100).all()
    return PrAnalysisListResponse(
        pr_analyses=[_to_summary(r) for r in records],
        total=len(records),
    )


# ============================================================
# Continuous repository health trend
# ============================================================

@router.get(
    "/repositories/{repository_id}/health-trend",
    response_model=HealthTrendResponse,
)
def get_health_trend(repository_id: int, db: Session = Depends(get_db)):
    """Health scores across the repository's analysis runs (oldest first)."""
    rows = db.query(RepositoryHealth).filter(
        RepositoryHealth.repository_id == repository_id
    ).order_by(RepositoryHealth.id.asc()).all()

    trend = [
        HealthTrendPoint(
            analysis_run_id=row.analysis_run_id,
            overall_score=row.overall_score,
            health_level=row.health_level,
            total_findings=row.total_findings,
            critical_findings=row.critical_findings,
            created_at=row.created_at,
        )
        for row in rows
    ]
    return HealthTrendResponse(repository_id=repository_id, trend=trend)