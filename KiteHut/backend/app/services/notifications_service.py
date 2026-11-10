"""
Smart Notifications Service (Phase 10).

Generates in-app notifications after a repository analysis completes by
comparing the new run against the previous run of the same repository:

    NEW_P0             - a P0 (critical) finding appeared that was not
                          present in the previous run
    CRITICAL_RESOLVED  - P0 findings from the previous run are gone
    HEALTH_DROP        - overall health score dropped significantly
    SECURITY_RISK      - new security-category findings appeared

Notifications are stored in the `notifications` table and, when
NOTIFICATION_WEBHOOK_URL is configured, POSTed as JSON to that URL
(e.g. Slack / Discord / a custom bot).
"""

import json
import logging

import httpx

from app.core.config import settings
from app.core.database import SessionLocal
from app.db_models.notification import Notification
from app.db_models.repository_health import RepositoryHealth
from app.db_models.finding import Finding

logger = logging.getLogger("repolens.notifications")

# Health score drop (points) required to trigger a HEALTH_DROP notice
HEALTH_DROP_THRESHOLD = 5.0


def generate_after_analysis(
    *,
    repository_id: int,
    analysis_run_id: int,
    repository_name: str,
) -> list[Notification]:
    """
    Compare the just-completed run with the previous run of the same
    repository and create notifications for meaningful changes.

    Returns the created Notification records (not yet committed by this
    function — callers commit through their own session).
    """
    db = SessionLocal()
    try:
        created: list[Notification] = []

        # Previous completed run (excluding the current one)
        from app.db_models.analysis_run import AnalysisRun

        previous = (
            db.query(AnalysisRun)
            .filter(
                AnalysisRun.repository_id == repository_id,
                AnalysisRun.status == "COMPLETED",
                AnalysisRun.id != analysis_run_id,
            )
            .order_by(AnalysisRun.id.desc())
            .first()
        )

        # Health scores
        new_health = db.query(RepositoryHealth).filter(
            RepositoryHealth.analysis_run_id == analysis_run_id
        ).first()
        prev_health = None
        if previous:
            prev_health = db.query(RepositoryHealth).filter(
                RepositoryHealth.analysis_run_id == previous.id
            ).first()

        # Findings
        new_findings = db.query(Finding).filter(
            Finding.analysis_run_id == analysis_run_id
        ).all()
        prev_findings = []
        if previous:
            prev_findings = db.query(Finding).filter(
                Finding.analysis_run_id == previous.id
            ).all()

        new_p0 = [f for f in new_findings if f.priority == "P0"]
        prev_p0 = [f for f in prev_findings if f.priority == "P0"]

        new_fingerprints = {f.fingerprint for f in new_findings}
        prev_fingerprints = {f.fingerprint for f in prev_findings}

        # 1. New P0 findings
        if new_p0:
            new_p0_fps = [f for f in new_p0 if f.fingerprint not in prev_fingerprints]
            if new_p0_fps:
                created.append(_make(
                    repository_id=repository_id,
                    kind="NEW_P0",
                    severity="critical",
                    title=f"🔴 New critical finding in {repository_name}",
                    message=(
                        f"{len(new_p0_fps)} new P0 finding(s) detected: "
                        + "; ".join(f.statement[:100] for f in new_p0_fps[:3])
                    ),
                ))

        # 2. Security risk introduced
        security_categories = {
            "security_risk", "security", "hardcoded_secret", "private_key",
        }
        new_sec = [
            f for f in new_findings
            if f.category in security_categories
            and f.fingerprint not in prev_fingerprints
        ]
        if new_sec:
            created.append(_make(
                repository_id=repository_id,
                kind="SECURITY_RISK",
                severity="warning",
                title=f"🔐 New security risk in {repository_name}",
                message=(
                    f"{len(new_sec)} new security finding(s) introduced "
                    f"(e.g. {new_sec[0].statement[:80]}...)"
                ),
            ))

        # 3. Critical issues resolved
        if prev_p0:
            resolved_p0 = [
                f for f in prev_p0 if f.fingerprint not in new_fingerprints
            ]
            if resolved_p0:
                created.append(_make(
                    repository_id=repository_id,
                    kind="CRITICAL_RESOLVED",
                    severity="info",
                    title=f"🟢 Critical issues resolved in {repository_name}",
                    message=(
                        f"{len(resolved_p0)} P0 finding(s) from the previous "
                        "analysis are no longer present."
                    ),
                ))

        # 4. Health dropped
        if new_health and prev_health:
            delta = prev_health.overall_score - new_health.overall_score
            if delta >= HEALTH_DROP_THRESHOLD:
                created.append(_make(
                    repository_id=repository_id,
                    kind="HEALTH_DROP",
                    severity="warning",
                    title=f"⚠️ Health dropped in {repository_name}",
                    message=(
                        f"Health score fell from {prev_health.overall_score:.0f} "
                        f"to {new_health.overall_score:.0f} (−{delta:.0f} points)."
                    ),
                ))

        if created:
            for notification in created:
                db.add(notification)
            db.commit()
            for notification in created:
                db.refresh(notification)

            # Fire the optional webhook after commit
            for notification in created:
                _deliver_webhook(notification, repository_name)

        return created
    finally:
        db.close()


def _make(
    *,
    repository_id: int,
    kind: str,
    severity: str,
    title: str,
    message: str,
) -> Notification:
    return Notification(
        repository_id=repository_id,
        kind=kind,
        severity=severity,
        title=title,
        message=message,
        read=False,
    )


def _deliver_webhook(notification: Notification, repository_name: str) -> None:
    """POST the notification to NOTIFICATION_WEBHOOK_URL (best effort)."""
    webhook_url = settings.NOTIFICATION_WEBHOOK_URL
    if not webhook_url:
        return
    payload = {
        "event": "notification",
        "kind": notification.kind,
        "severity": notification.severity,
        "repository": repository_name,
        "title": notification.title,
        "message": notification.message,
        "created_at": notification.created_at.isoformat()
        if notification.created_at else None,
    }
    try:
        response = httpx.post(webhook_url, json=payload, timeout=10.0)
        response.raise_for_status()
        logger.info("Notification webhook delivered (%s) -> %s",
                    notification.kind, response.status_code)
    except Exception as error:  # noqa: BLE001 - webhook must never crash analysis
        logger.warning("Notification webhook delivery failed: %s", error)