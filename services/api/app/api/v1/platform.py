"""Notifications, notification preferences, scan schedules, analytics, and cross-project
lists of scans and findings."""

import uuid
from typing import Annotated, NoReturn

from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy import select

from app.api.deps import Auth, DatabaseSession
from app.core.config import settings
from app.db.models.project import Project
from app.db.models.scan import Finding, TestRun
from app.repositories import scan as scan_repository
from app.schemas.analytics import AnalyticsOverview
from app.schemas.platform import (
    NotificationList,
    NotificationPreference,
    NotificationRead,
    PreferencesUpdate,
    ScheduleRead,
    ScheduleUpdate,
)
from app.schemas.scan import FindingRead, RunSummary, SeverityName
from app.services import analytics as analytics_service
from app.services import notifications as notification_service
from app.services import scan as scan_service
from app.services import schedules as schedule_service

router = APIRouter(tags=["platform"])


@router.get("/notifications", response_model=NotificationList)
async def list_notifications(
    auth: Auth,
    session: DatabaseSession,
    unread_only: bool = False,
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> NotificationList:
    items = await notification_service.list_notifications(
        session, auth.user.id, unread_only=unread_only, limit=limit, offset=offset
    )
    return NotificationList(
        items=[NotificationRead.model_validate(item) for item in items],
        unread_count=await notification_service.unread_count(session, auth.user.id),
    )


@router.post("/notifications/{notification_id}/read", status_code=status.HTTP_204_NO_CONTENT)
async def read_notification(
    notification_id: uuid.UUID, auth: Auth, session: DatabaseSession
) -> Response:
    await notification_service.mark_read(session, auth.user.id, notification_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/notifications/read-all")
async def read_all(auth: Auth, session: DatabaseSession) -> dict[str, int]:
    return {"updated": await notification_service.mark_read(session, auth.user.id)}


@router.get("/notifications/preferences", response_model=list[NotificationPreference])
async def get_preferences(auth: Auth, session: DatabaseSession) -> list[NotificationPreference]:
    prefs = await notification_service.preferences_for(session, auth.user.id)
    return [
        NotificationPreference(kind=kind, label=label, enabled=prefs[kind])
        for kind, label in notification_service.KINDS.items()
    ]


@router.put("/notifications/preferences", response_model=list[NotificationPreference])
async def update_preferences(
    data: PreferencesUpdate, auth: Auth, session: DatabaseSession
) -> list[NotificationPreference]:
    unknown = set(data.notifications) - set(notification_service.KINDS)
    if unknown:
        raise HTTPException(
            status_code=422, detail=f"Unknown notification kind: {sorted(unknown)[0]}"
        )
    prefs = await notification_service.update_preferences(session, auth.user.id, data.notifications)
    return [
        NotificationPreference(kind=kind, label=label, enabled=prefs[kind])
        for kind, label in notification_service.KINDS.items()
    ]


def _schedule_error(error: schedule_service.ScheduleError) -> NoReturn:
    raise HTTPException(status_code=error.status_code, detail=error.message) from error


@router.get("/projects/{project_id}/schedule", response_model=ScheduleRead | None)
async def get_schedule(
    project_id: uuid.UUID, auth: Auth, session: DatabaseSession
) -> ScheduleRead | None:
    try:
        _, schedule = await schedule_service.get_schedule(session, auth.user.id, project_id)
    except schedule_service.ScheduleError as error:
        _schedule_error(error)
    return ScheduleRead.model_validate(schedule) if schedule else None


@router.put("/projects/{project_id}/schedule", response_model=ScheduleRead)
async def save_schedule(
    project_id: uuid.UUID, data: ScheduleUpdate, auth: Auth, session: DatabaseSession
) -> ScheduleRead:
    try:
        schedule = await schedule_service.save_schedule(
            session,
            auth.user.id,
            project_id,
            enabled=data.enabled,
            frequency=data.frequency,
            hour_utc=data.hour_utc,
            weekday=data.weekday,
            interval_hours=data.interval_hours,
            config=settings,
        )
    except schedule_service.ScheduleError as error:
        _schedule_error(error)
    return ScheduleRead.model_validate(schedule)


@router.delete("/projects/{project_id}/schedule", status_code=status.HTTP_204_NO_CONTENT)
async def delete_schedule(project_id: uuid.UUID, auth: Auth, session: DatabaseSession) -> Response:
    try:
        deleted = await schedule_service.delete_schedule(session, auth.user.id, project_id)
    except schedule_service.ScheduleError as error:
        _schedule_error(error)
    if not deleted:
        raise HTTPException(status_code=404, detail="This project has no schedule.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/analytics/overview", response_model=AnalyticsOverview)
async def analytics_overview(
    auth: Auth,
    session: DatabaseSession,
    days: Annotated[int, Query(ge=1, le=365)] = 30,
    project_id: uuid.UUID | None = None,
) -> AnalyticsOverview:
    """Charts data computed from persisted scans only."""
    return await analytics_service.overview(session, auth.user.id, project_id=project_id, days=days)


@router.get("/scans", response_model=list[RunSummary])
async def recent_scans(
    auth: Auth,
    session: DatabaseSession,
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[RunSummary]:
    """Scans across all of the user's projects, newest first."""
    runs = await session.scalars(
        select(TestRun)
        .join(Project, Project.id == TestRun.project_id)
        .where(Project.owner_id == auth.user.id)
        .order_by(TestRun.created_at.desc(), TestRun.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return [scan_service.run_summary(run) for run in runs]


@router.get("/findings", response_model=list[FindingRead])
async def recent_findings(
    auth: Auth,
    session: DatabaseSession,
    severity: SeverityName | None = None,
    latest_only: bool = True,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[FindingRead]:
    """Findings across projects. By default only from each project's latest finished scan,
    so fixed issues do not linger."""
    query = (
        select(Finding)
        .join(Project, Project.id == Finding.project_id)
        .where(Project.owner_id == auth.user.id)
    )
    if latest_only:
        latest = await scan_repository.latest_runs_for_projects(
            session, None, finished_only=True, owner_id=auth.user.id
        )
        query = query.where(Finding.test_run_id.in_([run.id for run in latest.values()]))
    if severity is not None:
        query = query.where(Finding.severity == severity)
    order = scan_repository.severity_order()
    findings = await session.scalars(
        query.order_by(order, Finding.created_at.desc()).limit(limit).offset(offset)
    )
    return [FindingRead.model_validate(finding) for finding in findings]
