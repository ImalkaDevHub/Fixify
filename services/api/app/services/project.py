import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.project import Project
from app.repositories import project as project_repository
from app.schemas.project import ProjectCreate


async def create_project(session: AsyncSession, data: ProjectCreate) -> Project:
    return await project_repository.create_project(session, data)


async def list_projects(
    session: AsyncSession, *, limit: int, offset: int
) -> list[Project]:
    return await project_repository.list_projects(session, limit=limit, offset=offset)


async def count_projects(session: AsyncSession) -> int:
    return await project_repository.count_projects(session)


async def get_project(session: AsyncSession, project_id: uuid.UUID) -> Project | None:
    return await project_repository.get_project(session, project_id)


async def delete_project(session: AsyncSession, project_id: uuid.UUID) -> bool:
    project = await project_repository.get_project(session, project_id)
    if project is None:
        return False
    await project_repository.delete_project(session, project)
    return True
