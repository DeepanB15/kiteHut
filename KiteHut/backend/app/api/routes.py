from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.analysis import (
    AnalysisRequest,
    AnalysisJobResponse,
    JobStatusResponse,
)
from app.services.job_service import (
    create_job,
    get_job_status_dict,
    start_analysis_job,
)
from app.services.git_service import (
    InvalidRepositoryURL,
    RepositoryCloneError,
)


router = APIRouter(
    prefix="/api/v1",
    tags=["Repository Analysis"]
)


@router.post(
    "/analyze",
    response_model=AnalysisJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def analyze_repository(request: AnalysisRequest):
    """
    Queue a repository analysis.

    Phase 8: returns immediately with a job id; the analysis pipeline
    runs in the background. Poll GET /api/v1/jobs/{job_id} for status.
    """
    repository_url = str(request.repository_url)

    # Validate the URL up front so invalid input fails fast (400)
    # instead of inside the background job.
    try:
        from app.services.git_service import validate_github_repository_url
        validate_github_repository_url(repository_url)

    except InvalidRepositoryURL as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        )

    except RepositoryCloneError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(error),
        )

    job = create_job(repository_url)
    start_analysis_job(
        job.job_id,
        repository_url,
        mode=request.mode,
        enabled_agents=request.enabled_agents,
    )

    return AnalysisJobResponse(
        job_id=job.job_id,
        repository_url=repository_url,
        status=job.status,
        created_at=job.created_at,
    )


@router.get(
    "/jobs/{job_id}",
    response_model=JobStatusResponse,
)
def get_job_status(job_id: str, db: Session = Depends(get_db)):
    """
    Poll the status of an analysis job.

    Stages: PENDING -> CLONING -> SCANNING -> ANALYZING -> VERIFYING
            -> SCORING -> SAVING -> COMPLETED (or FAILED)
    """
    job = get_job_status_dict(job_id, db=db)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Analysis job not found",
        )
    return job