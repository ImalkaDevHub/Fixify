import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.db.models.project import Project
from app.repositories import project as project_repository
from app.repositories import scan as scan_repository
from app.schemas.project import ProjectCreate, ProjectUpdate
from app.services import site_verification


class ProjectError(Exception):
    status_code = 400

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class ProjectNotFoundError(ProjectError):
    status_code = 404


class ProjectLimitError(ProjectError):
    status_code = 429


async def create_project(
    session: AsyncSession, owner_id: uuid.UUID, data: ProjectCreate, config: Settings
) -> Project:
    if await project_repository.count_projects(session, owner_id) >= config.max_projects_per_user:
        raise ProjectLimitError(
            f"You can have at most {config.max_projects_per_user} projects. "
            "Delete one to add another."
        )
    project = Project(
        owner_id=owner_id,
        name=data.name,
        description=data.description,
        scan_max_links=data.scan_max_links,
        website_url=str(data.website_url),
        repo_full_name=data.repo_full_name,
        default_branch=data.default_branch,
    )
    return await project_repository.create_project(session, project)


async def list_projects(
    session: AsyncSession,
    owner_id: uuid.UUID,
    *,
    limit: int,
    offset: int,
    search: str | None = None,
) -> list[Project]:
    return await project_repository.list_projects(
        session, owner_id, limit=limit, offset=offset, search=search
    )


async def count_projects(session: AsyncSession, owner_id: uuid.UUID) -> int:
    return await project_repository.count_projects(session, owner_id)


async def get_project(
    session: AsyncSession, owner_id: uuid.UUID, project_id: uuid.UUID
) -> Project | None:
    return await project_repository.get_project(session, project_id, owner_id)


async def require_project(
    session: AsyncSession, owner_id: uuid.UUID, project_id: uuid.UUID
) -> Project:
    project = await project_repository.get_project(session, project_id, owner_id)
    if project is None:
        raise ProjectNotFoundError("Project not found.")
    return project


async def update_project(
    session: AsyncSession, owner_id: uuid.UUID, project_id: uuid.UUID, data: ProjectUpdate
) -> Project:
    project = await require_project(session, owner_id, project_id)
    changes = data.model_dump(exclude_unset=True)
    if "website_url" in changes and changes["website_url"] is not None:
        changes["website_url"] = str(changes["website_url"])
    for field, value in changes.items():
        if field in ("name", "website_url") and value is None:
            continue  # required fields cannot be cleared
        setattr(project, field, value)
    site_verification.reset_if_host_changed(project)
    if "repo_full_name" in changes:
        # A different repository invalidates the stored GitHub identity.
        project.github_repo_id = None
    return await project_repository.save(session, project)


async def delete_project(
    session: AsyncSession, owner_id: uuid.UUID, project_id: uuid.UUID
) -> list[uuid.UUID]:
    """Delete an owned project. Returns its run IDs so artifact files can be removed."""
    project = await require_project(session, owner_id, project_id)
    run_ids = await scan_repository.run_ids_for_project(session, project.id)
    await project_repository.delete_project(session, project)
    return run_ids
