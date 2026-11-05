"""Analytics from persisted scan results only. Empty data stays empty."""

import uuid
from collections import defaultdict
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.platform import FixProposal, PullRequest
from app.db.models.project import Project
from app.db.models.scan import Finding, TestRun
from app.repositories import scan as scan_repository
from app.schemas.analytics import (
    AnalyticsOverview,
    DailyPoint,
    ProjectHealth,
    ScanHistoryItem,
    SeverityTotals,
)

FINISHED = ("completed", "completed_with_errors")
# Health score of one scan: 100 minus weighted findings, floored at 0. Documented in the UI.
WEIGHTS = {"critical": 25, "high": 10, "medium": 4, "low": 1, "info": 0}
MAX_RUNS = 1_000


def run_health(run: TestRun) -> int:
    penalty = (
        WEIGHTS["critical"] * run.critical_count
        + WEIGHTS["high"] * run.high_count
        + WEIGHTS["medium"] * run.medium_count
        + WEIGHTS["low"] * run.low_count
    )
    return max(0, 100 - penalty)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _duration(run: TestRun) -> int | None:
    if run.started_at and run.finished_at:
        return max(
            0, int((_aware(run.finished_at) - _aware(run.started_at)).total_seconds() * 1000)
        )
    return None


async def overview(
    session: AsyncSession,
    owner_id: uuid.UUID,
    *,
    project_id: uuid.UUID | None = None,
    days: int = 30,
) -> AnalyticsOverview:
    since = datetime.now(UTC) - timedelta(days=days)
    owned = select(Project.id).where(Project.owner_id == owner_id)
    if project_id is not None:
        owned = owned.where(Project.id == project_id)
    projects = {
        project.id: project
        for project in await session.scalars(select(Project).where(Project.id.in_(owned)))
    }

    runs = list(
        await session.scalars(
            select(TestRun)
            .where(TestRun.project_id.in_(owned), TestRun.created_at >= since)
            .order_by(TestRun.created_at, TestRun.id)
            .limit(MAX_RUNS)
        )
    )
    finished = [run for run in runs if run.status in FINISHED]

    fingerprints: dict[uuid.UUID, set[str]] = defaultdict(set)
    if finished:
        rows = await session.execute(
            select(Finding.test_run_id, Finding.fingerprint).where(
                Finding.test_run_id.in_([run.id for run in finished])
            )
        )
        for run_id, fingerprint in rows.all():
            fingerprints[run_id].add(fingerprint)

    # The run before the window, per project, so the first run in the window has a baseline.
    # The last finished run before the window, per project, so the first run in the window has
    # a baseline. Two queries in total, whatever the number of projects.
    previous: dict[uuid.UUID, set[str] | None] = {pid: None for pid in projects}
    ranked = (
        select(
            TestRun.id,
            TestRun.project_id,
            func.row_number()
            .over(partition_by=TestRun.project_id, order_by=TestRun.created_at.desc())
            .label("position"),
        )
        .where(
            TestRun.project_id.in_(owned),
            TestRun.status.in_(FINISHED),
            TestRun.created_at < since,
        )
        .subquery()
    )
    baselines = dict(
        (run_id, project_id)
        for run_id, project_id in (
            await session.execute(
                select(ranked.c.id, ranked.c.project_id).where(ranked.c.position == 1)
            )
        ).all()
    )
    for project_id in baselines.values():
        previous[project_id] = set()
    if baselines:
        rows = await session.execute(
            select(Finding.test_run_id, Finding.fingerprint).where(
                Finding.test_run_id.in_(list(baselines))
            )
        )
        for run_id, fingerprint in rows.all():
            previous[baselines[run_id]].add(fingerprint)  # type: ignore[union-attr]

    daily: dict[str, dict[str, int | list[int]]] = defaultdict(
        lambda: {
            "scans": 0,
            "failed": 0,
            "new": 0,
            "resolved": 0,
            "critical": 0,
            "high": 0,
            "medium": 0,
            "low": 0,
            "info": 0,
            "health": [],
        }
    )
    total_new = total_resolved = 0
    for run in runs:
        day = _aware(run.created_at).date().isoformat()
        bucket = daily[day]
        bucket["scans"] += 1  # type: ignore[operator]
        if run.status == "failed":
            bucket["failed"] += 1  # type: ignore[operator]
        if run.status not in FINISHED:
            continue
        current = fingerprints.get(run.id, set())
        earlier = previous.get(run.project_id)
        if earlier is not None:
            new, resolved = len(current - earlier), len(earlier - current)
            bucket["new"] += new  # type: ignore[operator]
            bucket["resolved"] += resolved  # type: ignore[operator]
            total_new += new
            total_resolved += resolved
        previous[run.project_id] = current
        for severity in WEIGHTS:
            bucket[severity] += getattr(run, f"{severity}_count")  # type: ignore[operator]
        bucket["health"].append(run_health(run))  # type: ignore[union-attr]

    points = []
    for day in sorted(daily):
        bucket = daily[day]
        health_values: list[int] = bucket["health"]  # type: ignore[assignment]
        points.append(
            DailyPoint(
                date=day,
                scans=bucket["scans"],  # type: ignore[arg-type]
                failed_scans=bucket["failed"],  # type: ignore[arg-type]
                new_findings=bucket["new"],  # type: ignore[arg-type]
                resolved_findings=bucket["resolved"],  # type: ignore[arg-type]
                severity=SeverityTotals(**{s: bucket[s] for s in WEIGHTS}),  # type: ignore[arg-type]
                health=round(sum(health_values) / len(health_values)) if health_values else None,
            )
        )

    latest = await scan_repository.latest_runs_for_projects(
        session, list(projects), finished_only=True
    )
    current_totals = SeverityTotals(
        **{s: sum(getattr(run, f"{s}_count") for run in latest.values()) for s in WEIGHTS}
    )
    health = [
        ProjectHealth(
            project_id=pid,
            name=project.name,
            health=run_health(latest[pid]) if pid in latest else None,
            latest_scan_id=latest[pid].id if pid in latest else None,
            latest_scan_at=latest[pid].created_at if pid in latest else None,
            findings=latest[pid].findings_count if pid in latest else 0,
        )
        for pid, project in projects.items()
    ]
    durations = [d for d in (_duration(run) for run in finished) if d is not None]
    open_fixes = await session.scalar(
        select(func.count())
        .select_from(FixProposal)
        .where(FixProposal.project_id.in_(owned), FixProposal.status == "pending_review")
    )
    open_prs = await session.scalar(
        select(func.count())
        .select_from(PullRequest)
        .where(PullRequest.project_id.in_(owned), PullRequest.status == "open")
    )
    history = [
        ScanHistoryItem(
            id=run.id,
            project_id=run.project_id,
            project_name=projects[run.project_id].name if run.project_id in projects else "",
            status=run.status,
            trigger=run.trigger or "manual",
            created_at=run.created_at,
            duration_ms=_duration(run),
            findings=run.findings_count,
            critical=run.critical_count,
            high=run.high_count,
        )
        for run in reversed(runs[-20:])
    ]
    return AnalyticsOverview(
        days=days,
        project_count=len(projects),
        scan_count=len(runs),
        finished_scan_count=len(finished),
        failed_scan_count=sum(1 for run in runs if run.status == "failed"),
        active_scan_count=sum(1 for run in runs if run.status in ("queued", "running")),
        average_duration_ms=round(sum(durations) / len(durations)) if durations else None,
        current_findings=current_totals,
        new_findings=total_new,
        resolved_findings=total_resolved,
        open_fix_proposals=open_fixes or 0,
        open_pull_requests=open_prs or 0,
        daily=points,
        projects=health,
        recent_scans=history,
    )
