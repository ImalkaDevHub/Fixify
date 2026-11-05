"""In-app notifications. Created by the worker and API inside the caller's transaction."""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.platform import Notification, UserPreferences
from app.db.models.project import Project

KINDS: dict[str, str] = {
    "scan_started": "A scan starts",
    "scan_completed": "A scan completes",
    "scan_failed": "A scan fails",
    "critical_findings": "Critical findings are detected",
    "analysis_completed": "AI analysis is complete",
    "fix_ready": "A proposed fix is ready for review",
    "fix_validation_failed": "A proposed fix fails validation",
    "pull_request_created": "A pull request is created",
    "job_failed": "Background work fails",
}
# Off unless the user turns them on: they are frequent and rarely actionable.
_DEFAULT_OFF = frozenset({"scan_started"})


def enabled(preferences: dict[str, Any], kind: str) -> bool:
    value = preferences.get(kind)
    return kind not in _DEFAULT_OFF if value is None else bool(value)


async def preferences_for(session: AsyncSession, user_id: uuid.UUID) -> dict[str, bool]:
    stored = await session.get(UserPreferences, user_id)
    raw = stored.notifications if stored else {}
    return {kind: enabled(raw, kind) for kind in KINDS}


async def update_preferences(
    session: AsyncSession, user_id: uuid.UUID, changes: dict[str, bool]
) -> dict[str, bool]:
    stored = await session.get(UserPreferences, user_id)
    if stored is None:
        stored = UserPreferences(user_id=user_id, notifications={})
        session.add(stored)
    merged = dict(stored.notifications or {})
    merged.update({kind: bool(value) for kind, value in changes.items() if kind in KINDS})
    stored.notifications = merged  # reassign so the JSON column is marked dirty
    await session.commit()
    return await preferences_for(session, user_id)


async def owner_of_project(session: AsyncSession, project_id: uuid.UUID) -> uuid.UUID | None:
    return await session.scalar(select(Project.owner_id).where(Project.id == project_id))


async def notify(
    session: AsyncSession,
    *,
    user_id: uuid.UUID | None,
    kind: str,
    title: str,
    body: str = "",
    link: str | None = None,
    project_id: uuid.UUID | None = None,
    dedupe_key: str | None = None,
) -> Notification | None:
    """Add a notification unless the user disabled this kind or it was already sent.
    Does not commit: it becomes visible with the caller's transaction."""
    if user_id is None or kind not in KINDS:
        return None
    stored = await session.get(UserPreferences, user_id)
    if not enabled(stored.notifications if stored else {}, kind):
        return None
    if dedupe_key is not None:
        exists = await session.scalar(
            select(Notification.id).where(
                Notification.user_id == user_id, Notification.dedupe_key == dedupe_key
            )
        )
        if exists is not None:
            return None
    notification = Notification(
        user_id=user_id,
        kind=kind,
        title=title[:200],
        body=body[:1000],
        link=link[:500] if link else None,
        project_id=project_id,
        dedupe_key=dedupe_key[:200] if dedupe_key else None,
    )
    session.add(notification)
    await session.flush()
    return notification


async def list_notifications(
    session: AsyncSession, user_id: uuid.UUID, *, unread_only: bool, limit: int, offset: int
) -> list[Notification]:
    query = select(Notification).where(Notification.user_id == user_id)
    if unread_only:
        query = query.where(Notification.read_at.is_(None))
    result = await session.scalars(
        query.order_by(Notification.created_at.desc(), Notification.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(result)


async def unread_count(session: AsyncSession, user_id: uuid.UUID) -> int:
    count = await session.scalar(
        select(func.count())
        .select_from(Notification)
        .where(Notification.user_id == user_id, Notification.read_at.is_(None))
    )
    return count or 0


async def mark_read(
    session: AsyncSession, user_id: uuid.UUID, notification_id: uuid.UUID | None = None
) -> int:
    """Mark one (or, without an ID, all) of the user's notifications as read."""
    conditions = [Notification.user_id == user_id, Notification.read_at.is_(None)]
    if notification_id is not None:
        conditions.append(Notification.id == notification_id)
    result = await session.execute(
        update(Notification).where(*conditions).values(read_at=datetime.now(UTC))
    )
    await session.commit()
    return result.rowcount or 0
