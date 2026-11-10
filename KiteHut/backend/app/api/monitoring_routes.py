"""
Continuous Monitoring Guardian API and WebSocket Routes for RepoLens.

Endpoints for incremental change detection, impact routing, and real-time WebSocket file-watch streaming.
"""

import asyncio
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import (
    APIRouter,
    HTTPException,
    Query,
    WebSocket,
    WebSocketDisconnect,
    status,
)

from app.models.monitoring_api import (
    ChangeEventResponse,
    FindingSummaryResponse,
    MonitoringCheckRequest,
    MonitoringReportResponse,
    MonitoringStatusResponse,
)
from app.monitoring.models.change_event import MonitoringReport
from app.monitoring.watcher import RepoWatcher

logger = logging.getLogger("repolens.api.monitoring")

router = APIRouter(prefix="/api/v1/monitoring", tags=["Continuous Guardian Monitoring"])


def _report_to_response(report: MonitoringReport) -> MonitoringReportResponse:
    """Transform internal MonitoringReport to typed API response model."""
    changes = [
        ChangeEventResponse(
            event_id=ev.event_id,
            source=ev.source,
            file_path=ev.file_path,
            change_type=ev.change_type,
            diff_content=ev.diff_content,
            affected_symbols=ev.affected_symbols,
            timestamp=ev.timestamp,
            metadata=ev.metadata,
        )
        for ev in report.changed_events
    ]

    findings = [
        FindingSummaryResponse(
            finding_id=f.finding_id,
            category=f.category.value if hasattr(f.category, "value") else str(f.category),
            severity=f.severity.value if hasattr(f.severity, "value") else str(f.severity),
            title=f.title,
            description=f.description,
            file_path=f.file_path,
            line_number=f.line_number,
            priority=f.priority,
            truth_status=f.truth_status,
        )
        for f in report.new_findings
    ]

    categories = [
        cat.value if hasattr(cat, "value") else str(cat)
        for cat in report.triggered_categories
    ]

    return MonitoringReportResponse(
        report_id=report.report_id,
        timestamp=report.timestamp,
        changed_events=changes,
        impacted_files=report.impacted_files,
        triggered_categories=categories,
        new_findings=findings,
        resolved_findings_count=report.resolved_findings_count,
        duration_ms=report.duration_ms,
    )


@router.post(
    "/check",
    response_model=MonitoringReportResponse,
    summary="Trigger incremental repository monitoring check",
)
def trigger_monitoring_check(request: MonitoringCheckRequest):
    """
    Execute a single incremental monitoring tick.
    Detects git/filesystem changes, computes AST blast radius, and runs targeted specialist scans.
    """
    repo_path = Path(request.repository_path).resolve()
    if not repo_path.exists() or not repo_path.is_dir():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Repository path '{request.repository_path}' does not exist or is not a directory.",
        )

    try:
        watcher = RepoWatcher(str(repo_path))
        report = watcher.check_once()
        return _report_to_response(report)
    except Exception as error:
        logger.error("Monitoring check failed: %s", error)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Incremental monitoring check failed: {error}",
        )


@router.get(
    "/status",
    response_model=MonitoringStatusResponse,
    summary="Get repository monitoring guardian status",
)
def get_monitoring_status(repository_path: str = Query(".", description="Path to target repository")):
    """Inspect status and readiness of continuous monitoring guardian."""
    repo_path = Path(repository_path).resolve()
    if not repo_path.exists() or not repo_path.is_dir():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Repository path '{repository_path}' does not exist or is not a directory.",
        )

    return MonitoringStatusResponse(
        repository_path=str(repo_path),
        status="active",
        message="Continuous Guardian monitoring engine is initialized and active.",
        timestamp=datetime.now(timezone.utc),
    )


@router.websocket("/ws")
async def monitoring_websocket(websocket: WebSocket):
    """
    Real-time WebSocket stream for Continuous Guardian repository monitoring.
    Subscribers receive instant reports on file alterations, impacted AST symbols, and incremental findings.
    """
    await websocket.accept()

    current_repo_path: Optional[str] = None
    poll_interval: float = 3.0
    is_streaming: bool = False
    stream_task: Optional[asyncio.Task] = None
    async_loop = asyncio.get_running_loop()

    await websocket.send_json({
        "event": "connected",
        "message": "Connected to RepoLens Continuous Guardian WebSocket stream.",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    async def continuous_poll_loop():
        """Periodic background polling loop."""
        nonlocal current_repo_path, poll_interval
        try:
            while True:
                if current_repo_path:
                    try:
                        watcher = RepoWatcher(current_repo_path)
                        report = await async_loop.run_in_executor(None, watcher.check_once)
                        resp = _report_to_response(report)
                        # Always send report if changes exist, or heartbeat
                        if report.changed_events or report.new_findings:
                            await websocket.send_json({
                                "event": "changes_detected",
                                "report": resp.model_dump(mode="json"),
                            })
                        else:
                            await websocket.send_json({
                                "event": "monitoring_heartbeat",
                                "report": resp.model_dump(mode="json"),
                            })
                    except Exception as err:
                        logger.warning("Error during monitoring poll: %s", err)
                await asyncio.sleep(poll_interval)
        except asyncio.CancelledError:
            pass
        except Exception as err:
            logger.debug("Monitoring stream stopped: %s", err)

    try:
        while True:
            raw_text = await websocket.receive_text()
            try:
                data = json.loads(raw_text)
            except json.JSONDecodeError:
                await websocket.send_json({"event": "error", "message": "Invalid JSON payload."})
                continue

            action = data.get("action", "").lower()

            if action == "ping":
                await websocket.send_json({
                    "event": "pong",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })

            elif action == "subscribe":
                target_path = data.get("repository_path", ".")
                resolved = str(Path(target_path).resolve())
                if not Path(resolved).exists():
                    await websocket.send_json({
                        "event": "error",
                        "message": f"Repository path '{target_path}' does not exist.",
                    })
                    continue

                current_repo_path = resolved
                if "interval" in data:
                    try:
                        poll_interval = max(1.0, float(data["interval"]))
                    except (ValueError, TypeError):
                        pass

                if stream_task and not stream_task.done():
                    stream_task.cancel()

                stream_task = asyncio.create_task(continuous_poll_loop())
                is_streaming = True

                await websocket.send_json({
                    "event": "subscribed",
                    "repository_path": current_repo_path,
                    "interval": poll_interval,
                })

            elif action == "unsubscribe":
                if stream_task and not stream_task.done():
                    stream_task.cancel()
                is_streaming = False
                current_repo_path = None
                await websocket.send_json({
                    "event": "unsubscribed",
                    "message": "Continuous streaming paused.",
                })

            elif action == "check_now":
                target_path = data.get("repository_path") or current_repo_path or "."
                resolved = str(Path(target_path).resolve())
                try:
                    watcher = RepoWatcher(resolved)
                    report = await async_loop.run_in_executor(None, watcher.check_once)
                    resp = _report_to_response(report)
                    await websocket.send_json({
                        "event": "check_result",
                        "report": resp.model_dump(mode="json"),
                    })
                except Exception as err:
                    await websocket.send_json({
                        "event": "error",
                        "message": f"Manual check failed: {err}",
                    })

            else:
                await websocket.send_json({
                    "event": "warning",
                    "message": f"Unknown action '{action}'. Available: subscribe, unsubscribe, check_now, ping.",
                })

    except WebSocketDisconnect:
        logger.info("Monitoring WebSocket client disconnected.")
    finally:
        if stream_task and not stream_task.done():
            stream_task.cancel()
