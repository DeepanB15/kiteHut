"""
Phase 10 Product Routes.

Endpoints:
    PATCH /findings/{id}/status            update finding status lifecycle
    PATCH /pr-findings/{id}/status         update PR finding status lifecycle
    GET/PUT /repositories/{id}/quality-gate    custom quality gate rules
    GET  /repositories/{id}/trends         health + finding trends over runs
    GET  /analyses/{id}/report.md|.json|.pdf   downloadable reports
    GET  /notifications                    list notifications
    POST /notifications/{id}/read          mark one notification read
    POST /notifications/read-all           mark all notifications read
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.db_models.analysis_run import AnalysisRun
from app.db_models.finding import Finding
from app.db_models.notification import Notification
from app.db_models.pr_finding import PrFinding
from app.db_models.quality_gate_config import QualityGateConfig
from app.db_models.repository import Repository
from app.db_models.repository_health import RepositoryHealth
from app.models.pr_analysis import PrFindingResponse
from app.services import report_service

router = APIRouter(prefix="/api/v1", tags=["Product (Phase 10)"])

# Claim category -> trend bucket aliases
_CATEGORY_BUCKETS = {
    "security": {"security_risk", "security"},
    "architecture": {"architecture_issue", "architecture"},
    "quality": {"quality_issue", "quality"},
    "testing": {"testing_issue", "testing"},
}

# Valid status lifecycle values
FINDING_STATUSES = (
    "OPEN",
    "IN_PROGRESS",
    "RESOLVED",
    "IGNORED",
    "FALSE_POSITIVE",
    "ACCEPTED_RISK",
)


class FindingStatusUpdate(BaseModel):
    status: str = Field(..., description="New finding status")
    note: str | None = Field(None, description="Optional note explaining the change")


class QualityGateConfigUpdate(BaseModel):
    critical_limit: int = Field(0, ge=0, description="Max critical (P0) findings")
    security_limit: int = Field(0, ge=0, description="Max security findings")
    min_health: float = Field(60.0, ge=0, le=100, description="Min health score")


class TrendPoint(BaseModel):
    analysis_run_id: int
    created_at: datetime | None = None
    health_score: float | None = None
    health_level: str | None = None
    total_findings: int = 0
    p0: int = 0
    p1: int = 0
    p2: int = 0
    security: int = 0
    architecture: int = 0
    quality: int = 0
    testing: int = 0


class TrendResponse(BaseModel):
    repository_id: int
    trend: list[TrendPoint]


class NotificationResponse(BaseModel):
    id: int
    repository_id: int | None = None
    kind: str
    severity: str
    title: str
    message: str
    read: bool
    created_at: datetime


class NotificationListResponse(BaseModel):
    notifications: list[NotificationResponse]
    total: int
    unread: int


# ============================================================
# Finding status lifecycle
# ============================================================

@router.patch("/findings/{finding_id}/status")
def update_finding_status(
    finding_id: int,
    update: FindingStatusUpdate,
    db: Session = Depends(get_db),
):
    """Update the lifecycle status of a finding."""
    finding = db.query(Finding).filter(Finding.id == finding_id).first()
    if not finding:
        raise HTTPException(status_code=404, detail="Finding not found")

    new_status = update.status.upper()
    if new_status not in FINDING_STATUSES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid status. Valid values: {', '.join(FINDING_STATUSES)}",
        )

    finding.status = new_status
    finding.status_note = update.note
    finding.status_updated_at = datetime.now(timezone.utc)
    db.commit()

    return {
        "id": finding.id,
        "status": finding.status,
        "status_note": finding.status_note,
        "status_updated_at": finding.status_updated_at,
    }


@router.patch("/pr-findings/{finding_id}/status")
def update_pr_finding_status(
    finding_id: int,
    update: FindingStatusUpdate,
    db: Session = Depends(get_db),
):
    """Update the lifecycle status of a pull request finding."""
    finding = db.query(PrFinding).filter(PrFinding.id == finding_id).first()
    if not finding:
        raise HTTPException(status_code=404, detail="PR finding not found")

    new_status = update.status.upper()
    if new_status not in FINDING_STATUSES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid status. Valid values: {', '.join(FINDING_STATUSES)}",
        )

    finding.status = new_status
    finding.status_note = update.note
    db.commit()

    return {
        "id": finding.id,
        "status": finding.status,
        "status_note": finding.status_note,
    }


# ============================================================
# Custom quality gate rules
# ============================================================

def _gate_config_dict(config: QualityGateConfig | None) -> dict:
    if config is None:
        return {
            "critical_limit": None,
            "security_limit": None,
            "min_health": None,
            "uses_defaults": True,
        }
    return {
        "critical_limit": config.critical_limit,
        "security_limit": config.security_limit,
        "min_health": config.min_health,
        "uses_defaults": False,
    }


@router.get("/repositories/{repository_id}/quality-gate")
def get_quality_gate_config(repository_id: int, db: Session = Depends(get_db)):
    """Get the custom quality gate rules for a repository."""
    repo = db.query(Repository).filter(Repository.id == repository_id).first()
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")

    config = db.query(QualityGateConfig).filter(
        QualityGateConfig.repository_id == repository_id
    ).first()
    return _gate_config_dict(config)


@router.put("/repositories/{repository_id}/quality-gate")
def update_quality_gate_config(
    repository_id: int,
    update: QualityGateConfigUpdate,
    db: Session = Depends(get_db),
):
    """Set custom quality gate rules for a repository."""
    repo = db.query(Repository).filter(Repository.id == repository_id).first()
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")

    config = db.query(QualityGateConfig).filter(
        QualityGateConfig.repository_id == repository_id
    ).first()
    if config is None:
        config = QualityGateConfig(repository_id=repository_id)
        db.add(config)

    config.critical_limit = update.critical_limit
    config.security_limit = update.security_limit
    config.min_health = update.min_health
    config.updated_at = datetime.now(timezone.utc)
    db.commit()

    return _gate_config_dict(config)


# ============================================================
# Trends
# ============================================================

@router.get("/repositories/{repository_id}/trends", response_model=TrendResponse)
def get_repository_trends(repository_id: int, db: Session = Depends(get_db)):
    """
    Per-run health score and finding counts (oldest first) so the UI can
    plot repository health and security/quality/testing trends over time.
    """
    repo = db.query(Repository).filter(Repository.id == repository_id).first()
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")

    runs = db.query(AnalysisRun).filter(
        AnalysisRun.repository_id == repository_id,
        AnalysisRun.status == "COMPLETED",
    ).order_by(AnalysisRun.id.asc()).all()

    trend: list[TrendPoint] = []
    for run in runs:
        health = db.query(RepositoryHealth).filter(
            RepositoryHealth.analysis_run_id == run.id
        ).first()
        findings = db.query(Finding).filter(
            Finding.analysis_run_id == run.id
        ).all()

        counts = {"p0": 0, "p1": 0, "p2": 0,
                  "security": 0, "architecture": 0, "quality": 0, "testing": 0}
        for f in findings:
            if f.priority == "P0":
                counts["p0"] += 1
            elif f.priority == "P1":
                counts["p1"] += 1
            elif f.priority == "P2":
                counts["p2"] += 1
            # Normalize claim categories into the four trend buckets
            category = f.category
            for bucket, aliases in _CATEGORY_BUCKETS.items():
                if category in aliases:
                    counts[bucket] = counts.get(bucket, 0) + 1
                    break

        trend.append(TrendPoint(
            analysis_run_id=run.id,
            created_at=run.created_at,
            health_score=health.overall_score if health else None,
            health_level=health.health_level if health else None,
            total_findings=len(findings),
            **counts,
        ))

    return TrendResponse(repository_id=repository_id, trend=trend)


# ============================================================
# Reports
# ============================================================

@router.get("/analyses/{analysis_id}/report.json")
def get_json_report(analysis_id: int, db: Session = Depends(get_db)):
    """Download the analysis report as JSON."""
    try:
        content = report_service.build_json_report(db, analysis_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error))
    return Response(
        content=content,
        media_type="application/json",
        headers={
            "Content-Disposition":
                f'attachment; filename="repolens-analysis-{analysis_id}.json"',
        },
    )


@router.get("/analyses/{analysis_id}/report.md")
def get_markdown_report(analysis_id: int, db: Session = Depends(get_db)):
    """Download the analysis report as Markdown."""
    try:
        content = report_service.build_markdown_report(db, analysis_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error))
    return Response(
        content=content,
        media_type="text/markdown",
        headers={
            "Content-Disposition":
                f'attachment; filename="repolens-analysis-{analysis_id}.md"',
        },
    )


@router.get("/analyses/{analysis_id}/report.pdf")
def get_pdf_report(analysis_id: int, db: Session = Depends(get_db)):
    """Download the analysis report as a PDF document."""
    try:
        content = report_service.build_pdf_report(db, analysis_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error))
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error))
    return Response(
        content=content,
        media_type="application/pdf",
        headers={
            "Content-Disposition":
                f'attachment; filename="repolens-analysis-{analysis_id}.pdf"',
        },
    )


# ============================================================
# Notifications
# ============================================================

def _notification_response(n: Notification) -> NotificationResponse:
    return NotificationResponse(
        id=n.id,
        repository_id=n.repository_id,
        kind=n.kind,
        severity=n.severity,
        title=n.title,
        message=n.message,
        read=n.read,
        created_at=n.created_at,
    )


@router.get("/notifications", response_model=NotificationListResponse)
def list_notifications(
    unread_only: bool = Query(False),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """List notifications, newest first."""
    query = db.query(Notification)
    if unread_only:
        query = query.filter(Notification.read.is_(False))

    records = query.order_by(Notification.created_at.desc()).limit(limit).all()
    unread = db.query(Notification).filter(
        Notification.read.is_(False)
    ).count()

    return NotificationListResponse(
        notifications=[_notification_response(n) for n in records],
        total=len(records),
        unread=unread,
    )


@router.post("/notifications/{notification_id}/read")
def mark_notification_read(
    notification_id: int,
    db: Session = Depends(get_db),
):
    """Mark a single notification as read."""
    notification = db.query(Notification).filter(
        Notification.id == notification_id
    ).first()
    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")
    notification.read = True
    db.commit()
    return _notification_response(notification)


@router.post("/notifications/read-all")
def mark_all_notifications_read(db: Session = Depends(get_db)):
    """Mark all notifications as read."""
    updated = db.query(Notification).filter(
        Notification.read.is_(False)
    ).update({"read": True}, synchronize_session=False)
    db.commit()
    return {"updated": updated}