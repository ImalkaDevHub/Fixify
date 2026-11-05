import uuid
from collections.abc import AsyncIterator
from typing import Annotated, NoReturn

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse

from app.api.deps import Auth, DatabaseSession, VerifiedAuth
from app.core.config import settings
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
        403: {"description": "Email address not verified"},
        404: {"description": "Project not found"},
        409: {"description": "A scan for this project is already queued or running"},
        422: {"description": "Invalid options, or the target URL is blocked by policy"},
        429: {"description": "Too many queued scans"},
        503: {"description": "The scan queue is unavailable"},
    },
)
async def create_scan(
    project_id: uuid.UUID,
    auth: VerifiedAuth,
    session: DatabaseSession,
    queue: Annotated[ScanQueue, Depends(get_queue)],
    policy: Annotated[UrlPolicy, Depends(get_url_policy)],
    options: ScanCreate | None = None,
) -> ScanQueued:
    """Queue a scan of the project's website (or an allowed scan-specific URL)."""
    try:
        run = await scan_service.create_scan(
            session, queue, settings, auth.user.id, project_id, options or ScanCreate(), policy
        )
    except scan_service.ScanError as error:
        _raise(error)
    return ScanQueued.model_validate(run)


@router.get("/projects/{project_id}/scans", response_model=list[RunSummary], responses=_NOT_FOUND)
async def list_scans(
    project_id: uuid.UUID,
    auth: Auth,
    session: DatabaseSession,
    limit: Limit = 20,
    offset: Offset = 0,
) -> list[RunSummary]:
    """Scans for a project, newest first."""
    try:
        return await scan_service.list_scans(
            session, auth.user.id, project_id, limit=limit, offset=offset
        )
    except scan_service.ScanError as error:
        _raise(error)


@router.get(
    "/projects/{project_id}/findings", response_model=list[FindingRead], responses=_NOT_FOUND
)
async def list_project_findings(
    project_id: uuid.UUID,
    auth: Auth,
    session: DatabaseSession,
    severity: SeverityFilter = None,
    limit: Limit = 50,
    offset: Offset = 0,
) -> list[FindingRead]:
    """Findings across all scans of a project, newest first."""
    try:
        findings = await scan_service.list_project_findings(
            session, auth.user.id, project_id, severity=severity, limit=limit, offset=offset
        )
    except scan_service.ScanError as error:
        _raise(error)
    return [FindingRead.model_validate(finding) for finding in findings]


@router.get("/scans/summary", response_model=DashboardSummary)
async def dashboard_summary(auth: Auth, session: DatabaseSession) -> DashboardSummary:
    """Real counts for the signed-in user's dashboard."""
    return await scan_service.dashboard_summary(session, auth.user.id)


@router.get("/scans/{run_id}", response_model=RunDetail, responses=_NOT_FOUND)
async def get_scan(run_id: uuid.UUID, auth: Auth, session: DatabaseSession) -> RunDetail:
    """Status, counters, check results, and artifacts of one scan."""
    detail = await scan_service.get_scan(session, auth.user.id, run_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Scan not found.")
    return detail


@router.post(
    "/scans/{run_id}/cancel",
    response_model=RunSummary,
    responses={**_NOT_FOUND, 409: {"description": "The scan is no longer queued"}},
)
async def cancel_scan(run_id: uuid.UUID, auth: Auth, session: DatabaseSession) -> RunSummary:
    """Cancel a scan that has not started yet. Running scans cannot be cancelled."""
    try:
        return await scan_service.cancel_scan(session, auth.user.id, run_id)
    except scan_service.ScanError as error:
        _raise(error)


@router.get("/scans/{run_id}/findings", response_model=list[FindingRead], responses=_NOT_FOUND)
async def list_scan_findings(
    run_id: uuid.UUID,
    auth: Auth,
    session: DatabaseSession,
    severity: SeverityFilter = None,
    limit: Limit = 100,
    offset: Offset = 0,
) -> list[FindingRead]:
    """Findings of one scan, most severe first."""
    findings = await scan_service.list_run_findings(
        session, auth.user.id, run_id, severity=severity, limit=limit, offset=offset
    )
    if findings is None:
        raise HTTPException(status_code=404, detail="Scan not found.")
    return [FindingRead.model_validate(finding) for finding in findings]


@router.get("/scans/{run_id}/comparison", response_model=RunComparison, responses=_NOT_FOUND)
async def compare_scan(run_id: uuid.UUID, auth: Auth, session: DatabaseSession) -> RunComparison:
    """New and resolved findings compared with the project's previous finished scan."""
    comparison = await scan_service.compare_scan(session, auth.user.id, run_id)
    if comparison is None:
        raise HTTPException(status_code=404, detail="Scan not found.")
    return comparison


@router.get(
    "/scans/{run_id}/artifacts/{artifact_id}",
    response_class=FileResponse,
    responses={200: {"content": {"image/png": {}}}, **_NOT_FOUND},
)
async def get_artifact(
    run_id: uuid.UUID, artifact_id: uuid.UUID, auth: Auth, session: DatabaseSession
) -> FileResponse:
    """Serve an artifact of an owned scan. Paths are never taken from the request."""
    found = await scan_service.artifact_file(
        session, auth.user.id, settings.artifact_dir, run_id, artifact_id
    )
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
            "Cross-Origin-Resource-Policy": "same-origin",
            "Content-Disposition": "inline",
        },
    )


@router.get("/findings/{finding_id}", response_model=FindingDetail, responses=_NOT_FOUND)
async def get_finding(finding_id: uuid.UUID, auth: Auth, session: DatabaseSession) -> FindingDetail:
    """One finding with its sanitized evidence."""
    finding = await scan_service.get_finding(session, auth.user.id, finding_id)
    if finding is None:
        raise HTTPException(status_code=404, detail="Finding not found.")
    return finding
