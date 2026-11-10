"""
Async Analysis Job Service.

Phase 8: POST /analyze now creates a job and returns immediately.
A daemon background thread executes the full analysis pipeline and
updates the job's status/stage so clients can poll progress.

Status flow:
    PENDING -> CLONING -> SCANNING -> ANALYZING -> VERIFYING
    -> SCORING -> SAVING -> COMPLETED
    (any stage -> FAILED on error)
"""

import logging
import shutil
import threading
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.db_models.analysis_job import AnalysisJob
from app.services.analysis_service import run_analysis
from app.services.git_service import (
    WORKSPACE_DIR,
    InvalidRepositoryURL,
    RepositoryCloneError,
)

logger = logging.getLogger("repolens.jobs")

# All pipeline stages in execution order (for progress display)
REPOSITORY_STAGES = [
    "PENDING",
    "CLONING",
    "SCANNING",
    "ANALYZING",
    "VERIFYING",
    "SCORING",
    "SAVING",
    "COMPLETED",
]

PR_STAGES = [
    "PENDING",
    "FETCHING",
    "ANALYZING",
    "SAVING",
    "COMPLETED",
]

STAGE_SEQUENCE = REPOSITORY_STAGES

TERMINAL_STATUSES = {"COMPLETED", "FAILED"}


# ============================================================
# Job CRUD (each uses its own session so calls are thread-safe)
# ============================================================

def create_job(
    repository_url: str,
    *,
    job_type: str = "REPOSITORY",
    pull_number: int | None = None,
) -> AnalysisJob:
    """Create a new analysis job in PENDING status."""
    message = "Job queued. Analysis will start shortly."
    if job_type == "PR" and pull_number is not None:
        message = f"Pull request #{pull_number} analysis queued."
    job = AnalysisJob(
        job_id=str(uuid4()),
        repository_url=repository_url,
        job_type=job_type,
        pull_number=pull_number,
        status="PENDING",
        current_stage="PENDING",
        message=message,
    )
    db = SessionLocal()
    try:
        db.add(job)
        db.commit()
        db.refresh(job)
        return job
    finally:
        db.close()


def get_job(job_id: str) -> AnalysisJob | None:
    """Fetch a job by id."""
    db = SessionLocal()
    try:
        return db.get(AnalysisJob, job_id)
    finally:
        db.close()


def update_job(
    job_id: str,
    *,
    status: str | None = None,
    stage: str | None = None,
    message: str | None = None,
    error: str | None = None,
    analysis_run_id: int | None = None,
    pr_analysis_id: int | None = None,
) -> AnalysisJob | None:
    """Update a job's status/stage (safe to call from any thread)."""
    db = SessionLocal()
    try:
        job = db.get(AnalysisJob, job_id)
        if not job:
            return None

        if status is not None:
            job.status = status
        if stage is not None:
            job.current_stage = stage
        if message is not None:
            job.message = message
        if error is not None:
            job.error_message = error
        if analysis_run_id is not None:
            job.analysis_run_id = analysis_run_id
        if pr_analysis_id is not None:
            job.pr_analysis_id = pr_analysis_id

        if job.status in TERMINAL_STATUSES and job.completed_at is None:
            job.completed_at = datetime.now(timezone.utc)

        job.updated_at = datetime.now(timezone.utc)
        db.commit()
        return job
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


# ============================================================
# Background execution
# ============================================================

def start_analysis_job(
    job_id: str,
    repository_url: str,
    *,
    job_type: str = "REPOSITORY",
    pull_number: int | None = None,
    mode: str = "balanced",
    enabled_agents: list[str] | None = None,
) -> None:
    """Launch the analysis pipeline in a daemon background thread."""
    thread = threading.Thread(
        target=_execute_job,
        args=(job_id, repository_url, job_type, pull_number, mode, enabled_agents),
        name=f"repolens-{job_type.lower()}-job-{job_id[:8]}",
        daemon=True,
    )
    thread.start()
    logger.info(
        "%s job %s started for %s%s",
        job_type,
        job_id,
        repository_url,
        f" PR #{pull_number}" if pull_number else "",
    )


def _execute_job(
    job_id: str,
    repository_url: str,
    job_type: str,
    pull_number: int | None,
    mode: str = "balanced",
    enabled_agents: list[str] | None = None,
) -> None:
    """Run the analysis pipeline and update job status as it goes."""
    def progress(stage: str, message: str) -> None:
        update_job(job_id, status=stage, stage=stage, message=message)

    try:
        if job_type == "PR":
            _execute_pr_job(job_id, repository_url, pull_number, progress)
        else:
            _execute_repository_job(
                job_id, repository_url, progress, mode, enabled_agents
            )

    except InvalidRepositoryURL as error:
        logger.warning("Analysis job %s rejected URL: %s", job_id, error)
        update_job(job_id, status="FAILED",
                   message="Invalid repository URL", error=str(error))

    except RepositoryCloneError as error:
        logger.warning("Analysis job %s clone failed: %s", job_id, error)
        update_job(job_id, status="FAILED",
                   message="Repository clone failed", error=str(error))

    except Exception as error:  # noqa: BLE001 - defensive catch-all
        logger.exception("Analysis job %s crashed", job_id)
        update_job(job_id, status="FAILED",
                   message="Analysis failed", error=str(error))

    finally:
        # Clean up the cloned workspace (repository jobs only)
        workspace = WORKSPACE_DIR / job_id
        if workspace.exists():
            shutil.rmtree(workspace, ignore_errors=True)


def _execute_repository_job(
    job_id: str,
    repository_url: str,
    progress,
    mode: str = "balanced",
    enabled_agents: list[str] | None = None,
) -> None:
    """Full repository analysis pipeline (Phases 1-7)."""
    progress("CLONING", "Cloning repository...")
    result = run_analysis(
        repository_url,
        on_stage=progress,
        mode=mode,
        enabled_agents=enabled_agents,
    )

    if result.get("error"):
        # Analysis completed with an internal pipeline error.
        # Keep current_stage intact so clients can see where it failed.
        update_job(
            job_id,
            status="FAILED",
            message="Analysis failed",
            error=result["error"],
        )
        logger.error("Analysis job %s failed: %s", job_id, result["error"])
        return

    update_job(
        job_id,
        status="COMPLETED",
        stage="COMPLETED",
        message=(
            f"Analysis completed with {result.get('findings_count', 0)} findings."
        ),
        analysis_run_id=result.get("analysis_run_id"),
    )
    logger.info(
        "Analysis job %s completed (run #%s, %s findings)",
        job_id,
        result.get("analysis_run_id"),
        result.get("findings_count", 0),
    )


def _execute_pr_job(
    job_id: str,
    repository_url: str,
    pull_number: int | None,
    progress,
) -> None:
    """Pull request analysis pipeline (Phase 9)."""
    from app.services.pr_analysis_service import run_pr_analysis

    if not pull_number:
        raise InvalidRepositoryURL("A pull request number is required.")

    progress("FETCHING", f"Fetching pull request #{pull_number}...")
    result = run_pr_analysis(
        repository_url,
        pull_number,
        on_stage=progress,
    )

    if result.get("error"):
        update_job(
            job_id,
            status="FAILED",
            message="PR analysis failed",
            error=result["error"],
        )
        logger.error("PR job %s failed: %s", job_id, result["error"])
        return

    update_job(
        job_id,
        status="COMPLETED",
        stage="COMPLETED",
        message=(
            f"PR analysis completed with {result.get('findings_count', 0)} findings."
        ),
        pr_analysis_id=result.get("pr_analysis_id"),
    )
    logger.info(
        "PR job %s completed (pr_analysis #%s, %s findings)",
        job_id,
        result.get("pr_analysis_id"),
        result.get("findings_count", 0),
    )


def _job_to_dict(job: AnalysisJob) -> dict:
    """Convert a job model to a plain dict for API responses."""
    return {
        "job_id": job.job_id,
        "repository_url": job.repository_url,
        "job_type": job.job_type,
        "pull_number": job.pull_number,
        "status": job.status,
        "current_stage": job.current_stage,
        "message": job.message,
        "error_message": job.error_message,
        "analysis_run_id": job.analysis_run_id,
        "pr_analysis_id": job.pr_analysis_id,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
        "completed_at": job.completed_at,
    }


def get_job_status_dict(job_id: str, db: Session | None = None) -> dict | None:
    """Fetch job as a dict for API responses."""
    if db is not None:
        job = db.get(AnalysisJob, job_id)
    else:
        job = get_job(job_id)
    if job is None:
        return None
    return _job_to_dict(job)