"""Notifications for scan lifecycle events, sent by the worker. Best effort: a notification
failure is logged and never affects the scan itself."""

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models.project import Project
from app.db.models.scan import TestRun
from app.services import notifications

logger = logging.getLogger(__name__)


async def notify_run(
    sessions: async_sessionmaker[AsyncSession], run_id: uuid.UUID, event: str
) -> None:
    try:
        async with sessions() as session:
            run = await session.get(TestRun, run_id)
            project = await session.get(Project, run.project_id) if run else None
            if run is None or project is None or project.owner_id is None:
                return
            owner, link = project.owner_id, f"/scans/{run.id}"
            common = {"user_id": owner, "link": link, "project_id": project.id}
            if event == "started":
                await notifications.notify(
                    session,
                    kind="scan_started",
                    title=f"Scan started: {project.name}",
                    body=run.target_url,
                    dedupe_key=f"scan-started:{run.id}:{run.attempts}",
                    **common,
                )
            elif event == "finished" and run.status in ("completed", "completed_with_errors"):
                await notifications.notify(
                    session,
                    kind="scan_completed",
                    title=f"Scan completed: {project.name}",
                    body=f"{run.findings_count} finding(s): {run.critical_count} critical, "
                    f"{run.high_count} high, {run.medium_count} medium.",
                    dedupe_key=f"scan-done:{run.id}",
                    **common,
                )
                if run.critical_count:
                    await notifications.notify(
                        session,
                        kind="critical_findings",
                        title=f"{run.critical_count} critical issue(s) on {project.name}",
                        body="Open the scan report to see what broke.",
                        dedupe_key=f"scan-critical:{run.id}",
                        **common,
                    )
            elif event in ("failed", "finished") and run.status == "failed":
                await notifications.notify(
                    session,
                    kind="scan_failed",
                    title=f"Scan failed: {project.name}",
                    body=run.failure_reason or "The scan could not be completed.",
                    dedupe_key=f"scan-failed:{run.id}",
                    **common,
                )
            await session.commit()
    except Exception:  # noqa: BLE001
        logger.exception("Could not send notification for run %s (%s)", run_id, event)
