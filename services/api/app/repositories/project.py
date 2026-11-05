"""Project queries. Every user-facing query is scoped to an owner; there is no unscoped list."""

import uuid

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.project import Project
from app.db.models.scan import TestRun


async def create_project(session: AsyncSession, project: Project) -> Project:
    session.add(project)
    await session.commit()
    await session.refresh(project)
    return project


async def list_projects(
    session: AsyncSession,
    owner_id: uuid.UUID,
    *,
    limit: int,
    offset: int,
    search: str | None = None,
) -> list[Project]:
    query = select(Project).where(Project.owner_id == owner_id)
    if search:
        pattern = f"%{search.lower()}%"
        query = query.where(
            func.lower(Project.name).like(pattern) | func.lower(Project.website_url).like(pattern)
        )
    result = await session.scalars(
        query.order_by(Project.created_at.desc(), Project.id.desc()).limit(limit).offset(offset)
    )
    return list(result)


async def count_projects(session: AsyncSession, owner_id: uuid.UUID) -> int:
    result = await session.scalar(
        select(func.count()).select_from(Project).where(Project.owner_id == owner_id)
    )
    return result or 0


async def get_project(
    session: AsyncSession, project_id: uuid.UUID, owner_id: uuid.UUID
) -> Project | None:
    """The project, only if it belongs to owner_id. Other owners' projects look missing."""
    return await session.scalar(
        select(Project).where(Project.id == project_id, Project.owner_id == owner_id)
    )


async def get_project_unscoped(session: AsyncSession, project_id: uuid.UUID) -> Project | None:
    """For background workers only, which act on behalf of the project's owner."""
    return await session.get(Project, project_id)


async def save(session: AsyncSession, project: Project) -> Project:
    await session.commit()
    await session.refresh(project)
    return project


async def delete_project(session: AsyncSession, project: Project) -> None:
    await session.delete(project)
    await session.commit()


async def run_ids_for_owner(session: AsyncSession, owner_id: uuid.UUID) -> list[uuid.UUID]:
    result = await session.scalars(
        select(TestRun.id).join(Project, Project.id == TestRun.project_id).where(
            Project.owner_id == owner_id
        )
    )
    return list(result)


async def assign_orphans(session: AsyncSession, owner_id: uuid.UUID) -> int:
    result = await session.execute(
        update(Project).where(Project.owner_id.is_(None)).values(owner_id=owner_id)
    )
    await session.commit()
    return result.rowcount or 0
