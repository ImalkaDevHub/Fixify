"""Background jobs: enqueueing (idempotent per subject), status, and the claim protocol used by
the worker. PostgreSQL is the source of truth, exactly like scan runs."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.db.models.platform import BackgroundJob
from app.db.models.project import Project

ACTIVE_JOB_STATUSES = ("queued", "running")
AI_JOB_KINDS = ("analyze_finding", "generate_fix")


class JobError(Exception):
    """Raised by job handlers. `public_message` is shown to the user as the failure reason."""

    def __init__(self, public_message: str, *, retryable: bool = False) -> None:
        super().__init__(public_message)
        self.public_message = public_message
        self.retryable = retryable


class JobLimitError(Exception):
    status_code = 429

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def utcnow() -> datetime:
    return datetime.now(UTC)


async def active_job(
    session: AsyncSession, kind: str, subject_id: uuid.UUID
) -> BackgroundJob | None:
    return await session.scalar(
        select(BackgroundJob).where(
            BackgroundJob.kind == kind,
            BackgroundJob.subject_id == subject_id,
            BackgroundJob.status.in_(ACTIVE_JOB_STATUSES),
        )
    )


async def enqueue(
    session: AsyncSession,
    *,
    kind: str,
    owner_id: uuid.UUID,
    project_id: uuid.UUID,
    subject_id: uuid.UUID,
    payload: dict[str, Any] | None = None,
    config: Settings,
) -> tuple[BackgroundJob, bool]:
    """Returns (job, created). A second request for the same work returns the running job."""
    existing = await active_job(session, kind, subject_id)
    if existing is not None:
        return existing, False
    if kind in AI_JOB_KINDS:
        recent = await session.scalar(
            select(func.count())
            .select_from(BackgroundJob)
            .where(
                BackgroundJob.owner_id == owner_id,
                BackgroundJob.kind.in_(AI_JOB_KINDS),
                BackgroundJob.created_at >= utcnow() - timedelta(hours=1),
            )
        )
        if (recent or 0) >= config.ai_jobs_per_user_per_hour:
            raise JobLimitError(
                f"You can start at most {config.ai_jobs_per_user_per_hour} AI tasks per hour."
            )
    job = BackgroundJob(
        kind=kind,
        owner_id=owner_id,
        project_id=project_id,
        subject_id=subject_id,
        payload=payload or {},
        max_attempts=config.job_max_attempts,
        run_after=utcnow(),
    )
    session.add(job)
    await session.commit()
    await session.refresh(job)
    return job, True


async def get_owned_job(
    session: AsyncSession, owner_id: uuid.UUID, job_id: uuid.UUID
) -> BackgroundJob | None:
    return await session.scalar(
        select(BackgroundJob)
        .join(Project, Project.id == BackgroundJob.project_id)
        .where(BackgroundJob.id == job_id, Project.owner_id == owner_id)
        .execution_options(populate_existing=True)
    )


async def list_jobs(
    session: AsyncSession,
    owner_id: uuid.UUID,
    *,
    subject_id: uuid.UUID | None = None,
    kind: str | None = None,
    active_only: bool = False,
    limit: int = 20,
) -> list[BackgroundJob]:
    query = (
        select(BackgroundJob)
        .join(Project, Project.id == BackgroundJob.project_id)
        .where(Project.owner_id == owner_id)
    )
    if subject_id is not None:
        query = query.where(BackgroundJob.subject_id == subject_id)
    if kind is not None:
        query = query.where(BackgroundJob.kind == kind)
    if active_only:
        query = query.where(BackgroundJob.status.in_(ACTIVE_JOB_STATUSES))
    result = await session.scalars(
        query.order_by(BackgroundJob.created_at.desc(), BackgroundJob.id.desc()).limit(limit)
    )
    return list(result)


# --- Worker side -----------------------------------------------------------------------------


async def due_job_ids(session: AsyncSession, now: datetime, limit: int) -> list[uuid.UUID]:
    result = await session.scalars(
        select(BackgroundJob.id)
        .where(BackgroundJob.status == "queued", BackgroundJob.run_after <= now)
        .order_by(BackgroundJob.run_after, BackgroundJob.created_at)
        .limit(limit)
    )
    return list(result)


async def claim(session: AsyncSession, job_id: uuid.UUID, now: datetime) -> int | None:
    result = await session.execute(
        update(BackgroundJob)
        .where(BackgroundJob.id == job_id, BackgroundJob.status == "queued")
        .values(
            status="running",
            attempts=BackgroundJob.attempts + 1,
            started_at=now,
            heartbeat_at=now,
            updated_at=now,
        )
        .returning(BackgroundJob.attempts)
    )
    attempt = result.scalar_one_or_none()
    await session.commit()
    return attempt


async def transition(
    session: AsyncSession, job_id: uuid.UUID, attempt: int, **values: object
) -> bool:
    """Only the attempt that claimed the job may finish it."""
    result = await session.execute(
        update(BackgroundJob)
        .where(
            BackgroundJob.id == job_id,
            BackgroundJob.status == "running",
            BackgroundJob.attempts == attempt,
        )
        .values(updated_at=utcnow(), **values)
    )
    return result.rowcount == 1


async def touch(session: AsyncSession, job_id: uuid.UUID, attempt: int) -> None:
    await session.execute(
        update(BackgroundJob)
        .where(
            BackgroundJob.id == job_id,
            BackgroundJob.attempts == attempt,
            BackgroundJob.status == "running",
        )
        .values(heartbeat_at=utcnow())
    )
    await session.commit()


async def stale_jobs(session: AsyncSession, cutoff: datetime) -> list[BackgroundJob]:
    result = await session.scalars(
        select(BackgroundJob).where(
            BackgroundJob.status == "running", BackgroundJob.heartbeat_at < cutoff
        )
    )
    return list(result)
