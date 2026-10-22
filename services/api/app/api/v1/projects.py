import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.schemas.project import ProjectCreate, ProjectRead
from app.services import project as project_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/projects", tags=["projects"])
DatabaseSession = Annotated[AsyncSession, Depends(get_session)]


@router.post("", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
async def create_project(data: ProjectCreate, session: DatabaseSession) -> ProjectRead:
    try:
        return await project_service.create_project(session, data)
    except SQLAlchemyError as error:
        await session.rollback()
        logger.exception("Project creation failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to create project.",
        ) from error


@router.get("", response_model=list[ProjectRead])
async def list_projects(
    session: DatabaseSession,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[ProjectRead]:
    return await project_service.list_projects(session, limit=limit, offset=offset)


@router.get("/count")
async def count_projects(session: DatabaseSession) -> dict[str, int]:
    return {"total": await project_service.count_projects(session)}


@router.get("/{project_id}", response_model=ProjectRead)
async def get_project(project_id: uuid.UUID, session: DatabaseSession) -> ProjectRead:
    project = await project_service.get_project(session, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    return project


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(project_id: uuid.UUID, session: DatabaseSession) -> Response:
    try:
        deleted = await project_service.delete_project(session, project_id)
    except SQLAlchemyError as error:
        await session.rollback()
        logger.exception("Project deletion failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to delete project.",
        ) from error
    if not deleted:
        raise HTTPException(status_code=404, detail="Project not found.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
