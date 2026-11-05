import uuid
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from app.ai.provider import ai_status
from app.api.deps import Auth, DatabaseSession, VerifiedAuth
from app.core.config import settings
from app.repositories import scan as scan_repository
from app.schemas.platform import AIStatus, AnalysisRead, FindingAIState, JobRead
from app.services import analysis as analysis_service
from app.services import jobs as job_service

router = APIRouter(tags=["ai"])


@router.get("/ai/status", response_model=AIStatus)
async def get_ai_status(_auth: Auth) -> AIStatus:
    """Whether AI features are configured. Never exposes keys."""
    return AIStatus(**ai_status(settings))


@router.get("/findings/{finding_id}/ai", response_model=FindingAIState)
async def finding_ai_state(
    finding_id: uuid.UUID, auth: Auth, session: DatabaseSession
) -> FindingAIState:
    """Latest analysis plus the state of any analysis job, for polling."""
    if await scan_repository.get_owned_finding(session, finding_id, auth.user.id) is None:
        raise HTTPException(status_code=404, detail="Finding not found.")
    analysis = await analysis_service.latest_analysis(session, auth.user.id, finding_id)
    jobs = await job_service.list_jobs(
        session, auth.user.id, subject_id=finding_id, kind="analyze_finding", limit=1
    )
    last = jobs[0] if jobs else None
    active = last if last and last.status in job_service.ACTIVE_JOB_STATUSES else None
    return FindingAIState(
        ai=AIStatus(**ai_status(settings)),
        analysis=AnalysisRead.model_validate(analysis) if analysis else None,
        active_job=JobRead.model_validate(active) if active else None,
        last_job=JobRead.model_validate(last) if last else None,
    )


@router.post(
    "/findings/{finding_id}/analysis",
    response_model=JobRead,
    status_code=status.HTTP_202_ACCEPTED,
    responses={404: {}, 429: {}, 503: {"description": "AI is not configured"}},
)
async def analyze_finding(
    finding_id: uuid.UUID, auth: VerifiedAuth, session: DatabaseSession
) -> JobRead:
    """Queue an AI analysis of this finding (returns the running job if one exists)."""
    try:
        job = await analysis_service.request_analysis(session, auth.user.id, finding_id, settings)
    except analysis_service.AnalysisError as error:
        raise HTTPException(status_code=error.status_code, detail=error.message) from error
    return JobRead.model_validate(job)


@router.get("/jobs/{job_id}", response_model=JobRead)
async def get_job(job_id: uuid.UUID, auth: Auth, session: DatabaseSession) -> JobRead:
    job = await job_service.get_owned_job(session, auth.user.id, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    return JobRead.model_validate(job)


@router.get("/jobs", response_model=list[JobRead])
async def list_jobs(
    auth: Auth,
    session: DatabaseSession,
    subject_id: uuid.UUID | None = None,
    active: bool = False,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[JobRead]:
    jobs = await job_service.list_jobs(
        session, auth.user.id, subject_id=subject_id, active_only=active, limit=limit
    )
    return [JobRead.model_validate(job) for job in jobs]
