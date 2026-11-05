import uuid
from typing import Annotated, NoReturn

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import Auth, DatabaseSession, VerifiedAuth
from app.core.config import settings
from app.db.models.platform import FixProposal
from app.db.models.scan import Finding
from app.schemas.platform import (
    FileChangeRead,
    FixDetail,
    FixRequest,
    FixStatus,
    FixSummary,
    JobRead,
    PullRequestRead,
    RegenerateRequest,
    ReviewRead,
    ReviewRequest,
)
from app.services import fixes as fix_service

router = APIRouter(tags=["fixes"])


def _raise(error: fix_service.FixError) -> NoReturn:
    raise HTTPException(status_code=error.status_code, detail=error.message) from error


def summary(fix: FixProposal) -> FixSummary:
    return FixSummary(
        id=fix.id,
        project_id=fix.project_id,
        finding_id=fix.finding_id,
        status=fix.status,  # type: ignore[arg-type]
        version=fix.version,
        title=fix.title,
        confidence=fix.confidence,
        validation_status=fix.validation_status,
        repo_full_name=fix.repo_full_name,
        base_branch=fix.base_branch,
        files=[change["path"] for change in fix.changes],
        created_at=fix.created_at,
        updated_at=fix.updated_at,
    )


async def detail(session: DatabaseSession, fix: FixProposal) -> FixDetail:
    reviews = await fix_service.reviews_for(session, fix.id)
    pr = await fix_service.pull_request_for(session, fix.id)
    finding = await session.get(Finding, fix.finding_id)
    return FixDetail(
        **summary(fix).model_dump(),
        analysis_id=fix.analysis_id,
        parent_id=fix.parent_id,
        base_commit_sha=fix.base_commit_sha,
        explanation=fix.explanation,
        impact=fix.impact,
        validation_messages=list(fix.validation_messages),
        changes=[
            FileChangeRead(
                path=c["path"],
                language=c.get("language", "text"),
                start_line=int(c.get("start_line", 1)),
                original=c.get("original", ""),
                proposed=c.get("proposed", ""),
                edits=c.get("edits", []),
            )
            for c in fix.changes
        ],
        provider=fix.provider,
        model=fix.model,
        reviewed_at=fix.reviewed_at,
        reviews=[ReviewRead.model_validate(review) for review in reviews],
        pull_request=PullRequestRead.model_validate(pr) if pr else None,
        finding_title=finding.title if finding else None,
        finding_severity=finding.severity if finding else None,
    )


@router.post(
    "/findings/{finding_id}/fixes", response_model=JobRead, status_code=status.HTTP_202_ACCEPTED
)
async def generate_fix(
    finding_id: uuid.UUID, data: FixRequest, auth: VerifiedAuth, session: DatabaseSession
) -> JobRead:
    """Queue AI fix generation from the connected repository's real source files."""
    try:
        job = await fix_service.request_fix(
            session,
            auth.user.id,
            finding_id,
            file_paths=data.file_paths,
            instructions=data.instructions,
            parent_fix_id=None,
            config=settings,
        )
    except fix_service.FixError as error:
        _raise(error)
    return JobRead.model_validate(job)


@router.get("/fixes", response_model=list[FixSummary])
async def list_fixes(
    auth: Auth,
    session: DatabaseSession,
    project_id: uuid.UUID | None = None,
    finding_id: uuid.UUID | None = None,
    status_filter: Annotated[FixStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[FixSummary]:
    fixes = await fix_service.list_fixes(
        session,
        auth.user.id,
        project_id=project_id,
        finding_id=finding_id,
        status=status_filter,
        limit=limit,
        offset=offset,
    )
    return [summary(fix) for fix in fixes]


@router.get("/fixes/{fix_id}", response_model=FixDetail)
async def get_fix(fix_id: uuid.UUID, auth: Auth, session: DatabaseSession) -> FixDetail:
    fix = await fix_service.get_owned_fix(session, auth.user.id, fix_id)
    if fix is None:
        raise HTTPException(status_code=404, detail="Fix proposal not found.")
    return await detail(session, fix)


@router.post("/fixes/{fix_id}/reviews", response_model=FixDetail)
async def review_fix(
    fix_id: uuid.UUID, data: ReviewRequest, auth: VerifiedAuth, session: DatabaseSession
) -> FixDetail:
    """Approve, reject, reopen, or comment. Approval never pushes anything by itself."""
    try:
        fix = await fix_service.review(session, auth.user.id, fix_id, data.action, data.comment)
    except fix_service.FixError as error:
        _raise(error)
    return await detail(session, fix)


@router.post(
    "/fixes/{fix_id}/regenerate", response_model=JobRead, status_code=status.HTTP_202_ACCEPTED
)
async def regenerate_fix(
    fix_id: uuid.UUID, data: RegenerateRequest, auth: VerifiedAuth, session: DatabaseSession
) -> JobRead:
    fix = await fix_service.get_owned_fix(session, auth.user.id, fix_id)
    if fix is None:
        raise HTTPException(status_code=404, detail="Fix proposal not found.")
    if fix.status == "applied":
        raise HTTPException(status_code=409, detail="This fix already has a pull request.")
    try:
        job = await fix_service.request_fix(
            session,
            auth.user.id,
            fix.finding_id,
            file_paths=data.file_paths or [c["path"] for c in fix.changes],
            instructions=data.instructions,
            parent_fix_id=fix.id,
            config=settings,
        )
    except fix_service.FixError as error:
        _raise(error)
    return JobRead.model_validate(job)


@router.post(
    "/fixes/{fix_id}/pull-request", response_model=JobRead, status_code=status.HTTP_202_ACCEPTED
)
async def create_pull_request(
    fix_id: uuid.UUID, auth: VerifiedAuth, session: DatabaseSession
) -> JobRead:
    """Commit the approved fix to a new branch and open a pull request (never merged)."""
    try:
        job = await fix_service.request_pull_request(session, auth.user.id, fix_id, settings)
    except fix_service.FixError as error:
        _raise(error)
    return JobRead.model_validate(job)


@router.post("/fixes/{fix_id}/pull-request/refresh", response_model=PullRequestRead)
async def refresh_pull_request(
    fix_id: uuid.UUID, auth: Auth, session: DatabaseSession
) -> PullRequestRead:
    try:
        pr = await fix_service.refresh_pull_request(session, auth.user.id, fix_id, settings)
    except fix_service.FixError as error:
        _raise(error)
    return PullRequestRead.model_validate(pr)
