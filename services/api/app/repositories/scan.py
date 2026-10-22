import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import Case, Select, case, delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.scan import Finding, ScanArtifact, TestCaseResult, TestRun

ACTIVE_STATUSES = ("queued", "running")


async def create_run(
    session: AsyncSession, *, project_id: uuid.UUID, target_url: str, max_links: int
) -> TestRun:
    run = TestRun(
        project_id=project_id, status="queued", target_url=target_url, max_links=max_links
    )
    session.add(run)
    await session.commit()
    await session.refresh(run)
    return run


async def get_run(session: AsyncSession, run_id: uuid.UUID) -> TestRun | None:
    return await session.get(TestRun, run_id, populate_existing=True)


async def list_runs(
    session: AsyncSession, project_id: uuid.UUID, *, limit: int, offset: int
) -> list[TestRun]:
    result = await session.scalars(
        select(TestRun)
        .where(TestRun.project_id == project_id)
        .order_by(TestRun.created_at.desc(), TestRun.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(result)


async def count_runs(session: AsyncSession) -> int:
    return (await session.scalar(select(func.count()).select_from(TestRun))) or 0


async def count_active(session: AsyncSession, project_id: uuid.UUID | None = None) -> int:
    query = select(func.count()).select_from(TestRun).where(TestRun.status.in_(ACTIVE_STATUSES))
    if project_id is not None:
        query = query.where(TestRun.project_id == project_id)
    return (await session.scalar(query)) or 0


FINISHED_STATUSES = ("completed", "completed_with_errors")


async def latest_runs_for_projects(
    session: AsyncSession, project_ids: Sequence[uuid.UUID] | None, *, finished_only: bool = False
) -> dict[uuid.UUID, TestRun]:
    """Most recent run per project (all projects when project_ids is None)."""
    if project_ids is not None and not project_ids:
        return {}
    filters = []
    if project_ids is not None:
        filters.append(TestRun.project_id.in_(project_ids))
    if finished_only:
        filters.append(TestRun.status.in_(FINISHED_STATUSES))
    ranked = (
        select(
            TestRun.id,
            func.row_number()
            .over(
                partition_by=TestRun.project_id,
                order_by=(TestRun.created_at.desc(), TestRun.id.desc()),
            )
            .label("position"),
        )
        .where(*filters)
        .subquery()
    )
    runs = await session.scalars(
        select(TestRun).join(ranked, ranked.c.id == TestRun.id).where(ranked.c.position == 1)
    )
    return {run.project_id: run for run in runs}


async def claim_run(session: AsyncSession, run_id: uuid.UUID, now: datetime) -> int | None:
    """Atomically move a queued run to running. Returns the new attempt number, or None."""
    result = await session.execute(
        update(TestRun)
        .where(TestRun.id == run_id, TestRun.status == "queued")
        .values(
            status="running",
            attempts=TestRun.attempts + 1,
            started_at=now,
            heartbeat_at=now,
            updated_at=now,
        )
        .returning(TestRun.attempts)
    )
    attempt = result.scalar_one_or_none()
    await session.commit()
    return attempt


async def queued_run_ids(session: AsyncSession, limit: int) -> list[uuid.UUID]:
    result = await session.scalars(
        select(TestRun.id)
        .where(TestRun.status == "queued")
        .order_by(TestRun.created_at)
        .limit(limit)
    )
    return list(result)


async def touch_heartbeat(
    session: AsyncSession, run_id: uuid.UUID, attempt: int, now: datetime
) -> None:
    await session.execute(
        update(TestRun)
        .where(TestRun.id == run_id, TestRun.status == "running", TestRun.attempts == attempt)
        .values(heartbeat_at=now)
    )
    await session.commit()


async def stale_running_runs(session: AsyncSession, cutoff: datetime) -> list[TestRun]:
    result = await session.scalars(
        select(TestRun).where(TestRun.status == "running", TestRun.heartbeat_at < cutoff)
    )
    return list(result)


async def transition(
    session: AsyncSession,
    run_id: uuid.UUID,
    *,
    from_status: str,
    attempt: int | None = None,
    commit: bool = True,
    **values: object,
) -> bool:
    """Conditional status update; returns False if the run was no longer in from_status."""
    conditions = [TestRun.id == run_id, TestRun.status == from_status]
    if attempt is not None:
        conditions.append(TestRun.attempts == attempt)
    result = await session.execute(update(TestRun).where(*conditions).values(**values))
    if commit:
        await session.commit()
    return result.rowcount == 1


async def clear_results(session: AsyncSession, run_id: uuid.UUID) -> None:
    """Remove results from an earlier attempt so a retry can never duplicate them."""
    await session.execute(delete(Finding).where(Finding.test_run_id == run_id))
    await session.execute(delete(TestCaseResult).where(TestCaseResult.test_run_id == run_id))
    await session.execute(delete(ScanArtifact).where(ScanArtifact.test_run_id == run_id))


async def first_detected(
    session: AsyncSession, project_id: uuid.UUID, fingerprints: Sequence[str]
) -> dict[str, datetime]:
    if not fingerprints:
        return {}
    result = await session.execute(
        select(Finding.fingerprint, func.min(Finding.first_detected_at))
        .where(Finding.project_id == project_id, Finding.fingerprint.in_(fingerprints))
        .group_by(Finding.fingerprint)
    )
    return {fingerprint: detected for fingerprint, detected in result.all()}


def _findings_query(severity: str | None) -> Select[tuple[Finding]]:
    query = select(Finding)
    if severity is not None:
        query = query.where(Finding.severity == severity)
    return query


def _severity_order() -> Case[int]:
    return case(
        {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4},
        value=Finding.severity,
        else_=5,
    )


async def list_run_findings(
    session: AsyncSession, run_id: uuid.UUID, *, severity: str | None, limit: int, offset: int
) -> list[Finding]:
    result = await session.scalars(
        _findings_query(severity)
        .where(Finding.test_run_id == run_id)
        .order_by(_severity_order(), Finding.created_at, Finding.id)
        .limit(limit)
        .offset(offset)
    )
    return list(result)


async def list_project_findings(
    session: AsyncSession,
    project_id: uuid.UUID,
    *,
    severity: str | None,
    limit: int,
    offset: int,
) -> list[Finding]:
    result = await session.scalars(
        _findings_query(severity)
        .where(Finding.project_id == project_id)
        .order_by(Finding.created_at.desc(), _severity_order(), Finding.id)
        .limit(limit)
        .offset(offset)
    )
    return list(result)


async def run_fingerprints(session: AsyncSession, run_id: uuid.UUID) -> dict[str, Finding]:
    result = await session.scalars(select(Finding).where(Finding.test_run_id == run_id))
    return {finding.fingerprint: finding for finding in result}


async def previous_finished_run(session: AsyncSession, run: TestRun) -> TestRun | None:
    return await session.scalar(
        select(TestRun)
        .where(
            TestRun.project_id == run.project_id,
            TestRun.status.in_(FINISHED_STATUSES),
            TestRun.created_at <= run.created_at,
            TestRun.id != run.id,
        )
        .order_by(TestRun.created_at.desc(), TestRun.finished_at.desc())
        .limit(1)
    )


async def get_finding(session: AsyncSession, finding_id: uuid.UUID) -> Finding | None:
    return await session.get(Finding, finding_id)


async def list_checks(session: AsyncSession, run_id: uuid.UUID) -> list[TestCaseResult]:
    result = await session.scalars(
        select(TestCaseResult)
        .where(TestCaseResult.test_run_id == run_id)
        .order_by(TestCaseResult.started_at, TestCaseResult.check_type)
    )
    return list(result)


async def list_artifacts(session: AsyncSession, run_id: uuid.UUID) -> list[ScanArtifact]:
    result = await session.scalars(
        select(ScanArtifact)
        .where(ScanArtifact.test_run_id == run_id)
        .order_by(ScanArtifact.created_at)
    )
    return list(result)


async def get_artifact(
    session: AsyncSession, run_id: uuid.UUID, artifact_id: uuid.UUID
) -> ScanArtifact | None:
    return await session.scalar(
        select(ScanArtifact).where(
            ScanArtifact.id == artifact_id, ScanArtifact.test_run_id == run_id
        )
    )


async def run_ids_for_project(session: AsyncSession, project_id: uuid.UUID) -> list[uuid.UUID]:
    result = await session.scalars(select(TestRun.id).where(TestRun.project_id == project_id))
    return list(result)


async def all_run_ids(session: AsyncSession) -> set[str]:
    result = await session.scalars(select(TestRun.id))
    return {str(run_id) for run_id in result}
