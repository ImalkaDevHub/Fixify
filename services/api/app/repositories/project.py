import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.project import Project
from app.schemas.project import ProjectCreate


async def create_project(session: AsyncSession, data: ProjectCreate) -> Project:
    project = Project(
        name=data.name,
        website_url=str(data.website_url),
        repo_full_name=data.repo_full_name,
        default_branch=data.default_branch,
    )
    session.add(project)
    await session.commit()
    await session.refresh(project)
    return project


async def list_projects(
    session: AsyncSession, *, limit: int, offset: int
) -> list[Project]:
    result = await session.scalars(
        select(Project)
        .order_by(Project.created_at.desc(), Project.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(result)


async def count_projects(session: AsyncSession) -> int:
    result = await session.scalar(select(func.count()).select_from(Project))
    return result or 0


async def get_project(session: AsyncSession, project_id: uuid.UUID) -> Project | None:
    return await session.get(Project, project_id)


async def delete_project(session: AsyncSession, project: Project) -> None:
    await session.delete(project)
    await session.commit()
