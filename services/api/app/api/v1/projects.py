import logging
import uuid
from datetime import datetime
from typing import Annotated, NoReturn

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError

from app.api.deps import Auth, DatabaseSession, Limiter, VerifiedAuth, enforce_limit
from app.api.v1.scans import get_url_policy
from app.core.artifacts import delete_run_artifacts
from app.core.config import settings
from app.scanner.url_policy import UrlPolicy
from app.schemas.project import (
    ProjectCreate,
    ProjectRead,
    ProjectUpdate,
    ProjectWithLatestScan,
)
from app.services import project as project_service
from app.services import scan as scan_service
from app.services import site_verification

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/projects", tags=["projects"])


def _raise(error: project_service.ProjectError) -> NoReturn:
    raise HTTPException(status_code=error.status_code, detail=error.message) from error


@router.post("", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
async def create_project(data: ProjectCreate, auth: Auth, session: DatabaseSession) -> ProjectRead:
    try:
        return await project_service.create_project(session, auth.user.id, data, settings)
    except project_service.ProjectError as error:
        _raise(error)
    except SQLAlchemyError as error:
        await session.rollback()
        logger.exception("Project creation failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to create project.",
        ) from error


@router.get("", response_model=list[ProjectWithLatestScan])
async def list_projects(
    auth: Auth,
    session: DatabaseSession,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    search: Annotated[str | None, Query(max_length=100)] = None,
) -> list[ProjectWithLatestScan]:
    projects = await project_service.list_projects(
        session, auth.user.id, limit=limit, offset=offset, search=(search or "").strip() or None
    )
    latest = await scan_service.latest_scans(session, [project.id for project in projects])
    return [
        ProjectWithLatestScan.model_validate(project).model_copy(
            update={"latest_scan": latest.get(project.id)}
        )
        for project in projects
    ]


@router.get("/count")
async def count_projects(auth: Auth, session: DatabaseSession) -> dict[str, int]:
    return {"total": await project_service.count_projects(session, auth.user.id)}


@router.get("/{project_id}", response_model=ProjectWithLatestScan)
async def get_project(
    project_id: uuid.UUID, auth: Auth, session: DatabaseSession
) -> ProjectWithLatestScan:
    project = await project_service.get_project(session, auth.user.id, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    latest = await scan_service.latest_scans(session, [project.id])
    return ProjectWithLatestScan.model_validate(project).model_copy(
        update={"latest_scan": latest.get(project.id)}
    )


@router.patch("/{project_id}", response_model=ProjectRead)
async def update_project(
    project_id: uuid.UUID, data: ProjectUpdate, auth: Auth, session: DatabaseSession
) -> ProjectRead:
    try:
        return await project_service.update_project(session, auth.user.id, project_id, data)
    except project_service.ProjectError as error:
        _raise(error)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(project_id: uuid.UUID, auth: Auth, session: DatabaseSession) -> Response:
    try:
        run_ids = await project_service.delete_project(session, auth.user.id, project_id)
    except project_service.ProjectError as error:
        _raise(error)
    except SQLAlchemyError as error:
        await session.rollback()
        logger.exception("Project deletion failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to delete project.",
        ) from error
    for run_id in run_ids:  # scan rows cascade in the database; files are removed here
        delete_run_artifacts(settings.artifact_dir, run_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


class VerificationRead(BaseModel):
    required: bool
    verified: bool
    host: str
    verified_at: datetime | None
    method: str | None
    token: str
    meta_tag: str
    file_url: str


@router.get("/{project_id}/verification", response_model=VerificationRead)
async def get_verification(
    project_id: uuid.UUID, auth: Auth, session: DatabaseSession
) -> VerificationRead:
    """The project's verification token and how to publish it."""
    try:
        state = await site_verification.get_state(session, auth.user.id, project_id, settings)
    except site_verification.VerificationError as error:
        raise HTTPException(status_code=error.status_code, detail=error.message) from error
    return VerificationRead(**state.__dict__)


@router.post("/{project_id}/verification/check", response_model=VerificationRead)
async def check_verification(
    project_id: uuid.UUID,
    auth: VerifiedAuth,
    session: DatabaseSession,
    limiter: Limiter,
    policy: Annotated[UrlPolicy, Depends(get_url_policy)],
) -> VerificationRead:
    """Fetch the website (through the scanner's egress proxy) and look for the token."""
    await enforce_limit(
        limiter, f"verify-site:{project_id}", 20, 3_600, "Too many checks. Try again later."
    )
    try:
        state = await site_verification.check(session, auth.user.id, project_id, policy, settings)
    except site_verification.VerificationError as error:
        raise HTTPException(status_code=error.status_code, detail=error.message) from error
    return VerificationRead(**state.__dict__)
