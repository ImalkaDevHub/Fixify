import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Annotated, NoReturn

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_session
from app.repositories import scan as scan_repository
from app.scanner.url_policy import UrlPolicy
from app.schemas.scan import (
    DashboardSummary,
    FindingDetail,
    FindingRead,
    RunComparison,
    RunDetail,
    RunSummary,
    ScanCreate,
    ScanQueued,
    SeverityName,
)
from app.services import scan as scan_service
from app.worker.queue import ScanQueue, create_queue

router = APIRouter(tags=["scans"])
DatabaseSession = Annotated[AsyncSession, Depends(get_session)]
Limit = Annotated[int, Query(ge=1, le=100)]
Offset = Annotated[int, Query(ge=0)]
SeverityFilter = Annotated[SeverityName | None, Query(description="Only this severity.")]

_NOT_FOUND = {404: {"description": "Not found"}}


async def get_queue() -> AsyncIterator[ScanQueue]:
    queue = create_queue(settings)
    try:
        yield queue
    finally:
        await queue.close()


def get_url_policy() -> UrlPolicy:
    return UrlPolicy(scan_service.policy_config(settings))


def _raise(error: scan_service.ScanError) -> NoReturn:
    raise HTTPException(status_code=error.status_code, detail=error.message) from error


@router.post(
    "/projects/{project_id}/scans",
    response_model=ScanQueued,
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        404: {"description": "Project not found"},
        409: {"description": "A scan for this project is already queued or running"},
        422: {"description": "Invalid options, or the target URL is blocked by policy"},
        429: {"description": "Too many queued scans"},
        503: {"description": "The scan queue is unavailable"},
    },
)
async def create_scan(
    project_id: uuid.UUID,
    session: DatabaseSession,
    queue: Annotated[ScanQueue, Depends(get_queue)],
    policy: Annotated[UrlPolicy, Depends(get_url_policy)],
    options: ScanCreate | None = None,
) -> ScanQueued:
    """Queue a scan of the project's website (or an allowed scan-specific URL)."""
    try:
        run = await scan_service.create_scan(
            session, queue, settings, project_id, options or ScanCreate(), policy
        )
    except scan_service.ScanError as error:
        _raise(error)
    return ScanQueued.model_validate(run)


@router.get(
    "/projects/{project_id}/scans", response_model=list[RunSummary], responses=_NOT_FOUND
)
async def list_scans(
    project_id: uuid.UUID, session: DatabaseSession, limit: Limit = 20, offset: Offset = 0
) -> list[RunSummary]:
    """Scans for a project, newest first."""
    try:
        return await scan_service.list_scans(session, project_id, limit=limit, offset=offset)
    except scan_service.ScanError as error:
        _raise(error)


@router.get(
    "/projects/{project_id}/findings", response_model=list[FindingRead], responses=_NOT_FOUND
)
async def list_project_findings(
    project_id: uuid.UUID,
    session: DatabaseSession,
    severity: SeverityFilter = None,
    limit: Limit = 50,
    offset: Offset = 0,
) -> list[FindingRead]:
    """Findings across all scans of a project, newest first."""
    try:
        findings = await scan_service.list_project_findings(
            session, project_id, severity=severity, limit=limit, offset=offset
        )
    except scan_service.ScanError as error:
        _raise(error)
    return [FindingRead.model_validate(finding) for finding in findings]


@router.get("/scans/summary", response_model=DashboardSummary)
async def dashboard_summary(session: DatabaseSession) -> DashboardSummary:
    """Real counts for the dashboard."""
    return await scan_service.dashboard_summary(session)


@router.get("/scans/{run_id}", response_model=RunDetail, responses=_NOT_FOUND)
async def get_scan(run_id: uuid.UUID, session: DatabaseSession) -> RunDetail:
    """Status, counters, check results, and artifacts of one scan."""
    detail = await scan_service.get_scan(session, run_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Scan not found.")
    return detail


@router.post(
    "/scans/{run_id}/cancel",
    response_model=RunSummary,
    responses={**_NOT_FOUND, 409: {"description": "The scan is no longer queued"}},
)
async def cancel_scan(run_id: uuid.UUID, session: DatabaseSession) -> RunSummary:
    """Cancel a scan that has not started yet. Running scans cannot be cancelled."""
    run = await scan_repository.get_run(session, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Scan not found.")
    cancelled = await scan_repository.transition(
        session,
        run_id,
        from_status="queued",
        status="cancelled",
        failure_reason="Cancelled before it started.",
        finished_at=datetime.now(UTC),
    )
    if not cancelled:
        raise HTTPException(status_code=409, detail="Only queued scans can be cancelled.")
    run = await scan_repository.get_run(session, run_id)
    assert run is not None
    return scan_service.run_summary(run)


@router.get("/scans/{run_id}/findings", response_model=list[FindingRead], responses=_NOT_FOUND)
async def list_scan_findings(
    run_id: uuid.UUID,
    session: DatabaseSession,
    severity: SeverityFilter = None,
    limit: Limit = 100,
    offset: Offset = 0,
) -> list[FindingRead]:
    """Findings of one scan, most severe first."""
    findings = await scan_service.list_run_findings(
        session, run_id, severity=severity, limit=limit, offset=offset
    )
    if findings is None:
        raise HTTPException(status_code=404, detail="Scan not found.")
    return [FindingRead.model_validate(finding) for finding in findings]


@router.get("/scans/{run_id}/comparison", response_model=RunComparison, responses=_NOT_FOUND)
async def compare_scan(run_id: uuid.UUID, session: DatabaseSession) -> RunComparison:
    """New and resolved findings compared with the project's previous finished scan."""
    comparison = await scan_service.compare_scan(session, run_id)
    if comparison is None:
        raise HTTPException(status_code=404, detail="Scan not found.")
    return comparison


@router.get(
    "/scans/{run_id}/artifacts/{artifact_id}",
    response_class=FileResponse,
    responses={200: {"content": {"image/png": {}}}, **_NOT_FOUND},
)
async def get_artifact(
    run_id: uuid.UUID, artifact_id: uuid.UUID, session: DatabaseSession
) -> FileResponse:
    """Serve an artifact that belongs to this scan. Paths are never taken from the request."""
    found = await scan_service.artifact_file(session, settings.artifact_dir, run_id, artifact_id)
    if found is None:
        raise HTTPException(status_code=404, detail="Artifact not found.")
    artifact, path = found
    return FileResponse(
        path,
        media_type=artifact.content_type,
        headers={
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'",
            "Cache-Control": "private, max-age=3600",
            "Content-Disposition": "inline",
        },
    )


@router.get("/findings/{finding_id}", response_model=FindingDetail, responses=_NOT_FOUND)
async def get_finding(finding_id: uuid.UUID, session: DatabaseSession) -> FindingDetail:
    """One finding with its sanitized evidence."""
    finding = await scan_service.get_finding(session, finding_id)
    if finding is None:
        raise HTTPException(status_code=404, detail="Finding not found.")
    return finding
