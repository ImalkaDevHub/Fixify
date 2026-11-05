"""Scheduled scans. The worker claims a due schedule with a conditional update on next_run_at,
so several workers never start the same scheduled scan twice."""

import logging
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.db.models.platform import ScanSchedule
from app.db.models.project import Project
from app.db.models.user import User
from app.repositories import project as project_repository
from app.schemas.scan import ScanCreate
from app.services import notifications
from app.services import scan as scan_service
from app.worker.queue import ScanQueue

logger = logging.getLogger(__name__)


class ScheduleError(Exception):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def next_run(schedule: ScanSchedule, after: datetime) -> datetime:
    after = aware(after)
    if schedule.frequency == "custom":
        return after + timedelta(hours=schedule.interval_hours or 24)
    candidate = after.replace(hour=schedule.hour_utc, minute=0, second=0, microsecond=0)
    if schedule.frequency == "weekly":
        weekday = schedule.weekday if schedule.weekday is not None else 0
        candidate += timedelta(days=(weekday - candidate.weekday()) % 7)
        if candidate <= after:
            candidate += timedelta(days=7)
        return candidate
    if candidate <= after:
        candidate += timedelta(days=1)
    return candidate


async def get_schedule(
    session: AsyncSession, owner_id: uuid.UUID, project_id: uuid.UUID
) -> tuple[Project, ScanSchedule | None]:
    project = await project_repository.get_project(session, project_id, owner_id)
    if project is None:
        raise ScheduleError("Project not found.", 404)
    schedule = await session.scalar(
        select(ScanSchedule).where(ScanSchedule.project_id == project.id)
    )
    return project, schedule


async def save_schedule(
    session: AsyncSession,
    owner_id: uuid.UUID,
    project_id: uuid.UUID,
    *,
    enabled: bool,
    frequency: str,
    hour_utc: int,
    weekday: int | None,
    interval_hours: int | None,
    config: Settings,
) -> ScanSchedule:
    project, schedule = await get_schedule(session, owner_id, project_id)
    if frequency == "custom":
        if interval_hours is None or interval_hours < config.min_schedule_interval_hours:
            raise ScheduleError(
                f"Custom schedules run at most every {config.min_schedule_interval_hours} hours.",
                422,
            )
    if frequency == "weekly" and weekday is None:
        raise ScheduleError("Choose a weekday for a weekly schedule.", 422)
    if schedule is None:
        schedule = ScanSchedule(project_id=project.id)
        session.add(schedule)
    schedule.enabled = enabled
    schedule.frequency = frequency
    schedule.hour_utc = hour_utc
    schedule.weekday = weekday if frequency == "weekly" else None
    schedule.interval_hours = interval_hours if frequency == "custom" else None
    schedule.next_run_at = next_run(schedule, datetime.now(UTC)) if enabled else None
    await session.commit()
    await session.refresh(schedule)
    return schedule


async def delete_schedule(
    session: AsyncSession, owner_id: uuid.UUID, project_id: uuid.UUID
) -> bool:
    _, schedule = await get_schedule(session, owner_id, project_id)
    if schedule is None:
        return False
    await session.delete(schedule)
    await session.commit()
    return True


async def _claim(session: AsyncSession, schedule: ScanSchedule, now: datetime) -> bool:
    expected = schedule.next_run_at
    result = await session.execute(
        update(ScanSchedule)
        .where(
            ScanSchedule.id == schedule.id,
            ScanSchedule.enabled.is_(True),
            ScanSchedule.next_run_at == expected,
        )
        .values(next_run_at=next_run(schedule, now), last_run_at=now)
    )
    await session.commit()
    return result.rowcount == 1


async def run_due_schedules(
    sessions: async_sessionmaker[AsyncSession],
    queue: ScanQueue,
    config: Settings,
    now: datetime | None = None,
) -> int:
    """Start every due scheduled scan once. Returns how many scans were queued."""
    now = now or datetime.now(UTC)
    async with sessions() as session:
        due = list(
            await session.scalars(
                select(ScanSchedule)
                .where(ScanSchedule.enabled.is_(True), ScanSchedule.next_run_at <= now)
                .order_by(ScanSchedule.next_run_at)
                .limit(20)
            )
        )
    started = 0
    for schedule in due:
        async with sessions() as session:
            if not await _claim(session, schedule, now):
                continue  # another worker took it
            project = await session.get(Project, schedule.project_id)
            owner = (
                await session.get(User, project.owner_id) if project and project.owner_id else None
            )
            outcome = "queued"
            run_id = None
            if owner is None or not owner.is_active:
                outcome = "skipped: the project has no active owner"
            elif config.require_email_verification and owner.email_verified_at is None:
                outcome = "skipped: the owner's email address is not verified"
            else:
                try:
                    run = await scan_service.create_scan(
                        session,
                        queue,
                        config,
                        owner.id,
                        schedule.project_id,
                        ScanCreate(),
                        trigger="scheduled",
                    )
                    run_id, started = run.id, started + 1
                except scan_service.ScanError as error:
                    outcome = f"not started: {error.message}"
            values: dict[str, object] = {"last_outcome": outcome[:200]}
            if run_id is not None:
                values["last_run_id"] = run_id
            await session.execute(
                update(ScanSchedule).where(ScanSchedule.id == schedule.id).values(**values)
            )
            if run_id is None and owner is not None and project is not None:
                await notifications.notify(
                    session,
                    user_id=owner.id,
                    kind="scan_failed",
                    title=f"Scheduled scan of {project.name} did not start",
                    body=outcome,
                    link=f"/projects/{project.id}",
                    project_id=project.id,
                    dedupe_key=f"schedule:{schedule.id}:{now.isoformat()}",
                )
            await session.commit()
            logger.info("Scheduled scan for project %s: %s", schedule.project_id, outcome)
    return started
