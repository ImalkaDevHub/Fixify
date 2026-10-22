"""Scan business logic used by the API: creating runs, reading results, comparing scans."""

import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.artifacts import ArtifactPathError, resolve_artifact_path
from app.core.config import Settings
from app.db.models.scan import Finding, ScanArtifact, TestRun
from app.repositories import project as project_repository
from app.repositories import scan as scan_repository
from app.scanner.contract import PolicyConfig, ScanLimits
from app.scanner.url_policy import (
    BlockedDestinationError,
    UnresolvableHostError,
    UrlPolicy,
)
from app.schemas.scan import (
    ArtifactRead,
    ComparisonFinding,
    DashboardSummary,
    FindingDetail,
    LatestScan,
    RunComparison,
    RunDetail,
    RunSummary,
    ScanCreate,
    SeverityCounts,
)
from app.worker.queue import QueueUnavailableError, ScanQueue

logger = logging.getLogger(__name__)

# Display order of the check catalog (matches the order the scanner runs them in).
CHECK_ORDER = (
    "page_navigation",
    "console_errors",
    "uncaught_exceptions",
    "failed_requests",
    "http_errors",
    "screenshot",
    "page_basics",
    "broken_links",
)


class ScanError(Exception):
    status_code = 400

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class ProjectNotFoundError(ScanError):
    status_code = 404


class TargetNotAllowedError(ScanError):
    status_code = 422


class ScanConflictError(ScanError):
    status_code = 409


class ScanCapacityError(ScanError):
    status_code = 429


class QueueSubmissionError(ScanError):
    status_code = 503


def policy_config(settings: Settings) -> PolicyConfig:
    ports = {int(port) for port in settings.scanner_allowed_ports.split(",") if port.strip()}
    hosts = {
        host.strip().lower() for host in settings.scanner_unsafe_allowed_hosts.split(",")
    } - {""}
    return PolicyConfig(allowed_ports=frozenset(ports), unsafe_allowed_hosts=frozenset(hosts))


def scan_limits(settings: Settings, max_links: int) -> ScanLimits:
    return ScanLimits(
        navigation_timeout_seconds=settings.scanner_navigation_timeout_seconds,
        max_scan_duration_seconds=settings.scanner_max_scan_duration_seconds,
        max_links=max_links,
        link_concurrency=settings.scanner_link_concurrency,
        link_timeout_seconds=settings.scanner_link_timeout_seconds,
        viewport_width=settings.scanner_viewport_width,
        viewport_height=settings.scanner_viewport_height,
        max_screenshot_bytes=settings.artifact_max_bytes,
    )


async def create_scan(
    session: AsyncSession,
    queue: ScanQueue,
    settings: Settings,
    project_id: uuid.UUID,
    options: ScanCreate,
    policy: UrlPolicy | None = None,
) -> TestRun:
    project = await project_repository.get_project(session, project_id)
    if project is None:
        raise ProjectNotFoundError("Project not found.")
    target_url = str(options.target_url) if options.target_url else project.website_url
    max_links = min(
        options.max_links if options.max_links is not None else settings.scanner_max_links,
        settings.scanner_max_links,
    )

    policy = policy or UrlPolicy(policy_config(settings))
    try:
        await policy.check_url(target_url)
    except BlockedDestinationError as error:
        raise TargetNotAllowedError(f"This URL cannot be scanned: {error}") from error
    except UnresolvableHostError:
        pass  # scanned anyway; the scan reports the site as unreachable

    if await scan_repository.count_active(session, project_id):
        raise ScanConflictError("A scan for this project is already queued or running.")
    if await scan_repository.count_active(session) >= settings.scanner_max_queued_scans:
        raise ScanCapacityError("Too many scans are waiting. Try again in a few minutes.")

    run = await scan_repository.create_run(
        session, project_id=project_id, target_url=target_url, max_links=max_links
    )
    try:
        await queue.enqueue(run.id)
    except QueueUnavailableError as error:
        # Never leave a queued run that no queue knows about.
        await scan_repository.transition(
            session,
            run.id,
            from_status="queued",
            status="failed",
            failure_reason="The scan could not be queued because the job queue is unavailable.",
            finished_at=datetime.now(UTC),
        )
        logger.warning("Scan %s could not be queued", run.id)
        raise QueueSubmissionError(
            "The scan queue is unavailable, so the scan was not started."
        ) from error
    return run


def artifact_read(artifact: ScanArtifact) -> ArtifactRead:
    return ArtifactRead(
        id=artifact.id,
        kind=artifact.kind,
        content_type=artifact.content_type,
        size_bytes=artifact.size_bytes,
        width=artifact.width,
        height=artifact.height,
        created_at=artifact.created_at,
        url=f"/api/v1/scans/{artifact.test_run_id}/artifacts/{artifact.id}",
    )


def run_summary(run: TestRun) -> RunSummary:
    duration = None
    if run.started_at and run.finished_at:
        duration = max(0, int((run.finished_at - run.started_at).total_seconds() * 1000))
    return RunSummary(
        id=run.id,
        project_id=run.project_id,
        status=run.status,  # type: ignore[arg-type]
        target_url=run.target_url,
        final_url=run.final_url,
        failure_reason=run.failure_reason,
        attempts=run.attempts,
        max_links=run.max_links,
        checks_total=run.checks_total,
        checks_passed=run.checks_passed,
        checks_failed=run.checks_failed,
        checks_errored=run.checks_errored,
        checks_skipped=run.checks_skipped,
        findings_count=run.findings_count,
        severity_counts=SeverityCounts(
            critical=run.critical_count,
            high=run.high_count,
            medium=run.medium_count,
            low=run.low_count,
            info=run.info_count,
        ),
        started_at=run.started_at,
        finished_at=run.finished_at,
        duration_ms=duration,
        created_at=run.created_at,
        updated_at=run.updated_at,
    )


async def list_scans(
    session: AsyncSession, project_id: uuid.UUID, *, limit: int, offset: int
) -> list[RunSummary]:
    if await project_repository.get_project(session, project_id) is None:
        raise ProjectNotFoundError("Project not found.")
    runs = await scan_repository.list_runs(session, project_id, limit=limit, offset=offset)
    return [run_summary(run) for run in runs]


async def get_scan(session: AsyncSession, run_id: uuid.UUID) -> RunDetail | None:
    run = await scan_repository.get_run(session, run_id)
    if run is None:
        return None
    checks = sorted(
        await scan_repository.list_checks(session, run_id),
        key=lambda check: (
            CHECK_ORDER.index(check.check_type) if check.check_type in CHECK_ORDER else 99
        ),
    )
    artifacts = await scan_repository.list_artifacts(session, run_id)
    return RunDetail(
        **run_summary(run).model_dump(),
        checks=checks,  # type: ignore[arg-type]
        artifacts=[artifact_read(artifact) for artifact in artifacts],
    )


async def list_run_findings(
    session: AsyncSession,
    run_id: uuid.UUID,
    *,
    severity: str | None,
    limit: int,
    offset: int,
) -> list[Finding] | None:
    if await scan_repository.get_run(session, run_id) is None:
        return None
    return await scan_repository.list_run_findings(
        session, run_id, severity=severity, limit=limit, offset=offset
    )


async def list_project_findings(
    session: AsyncSession,
    project_id: uuid.UUID,
    *,
    severity: str | None,
    limit: int,
    offset: int,
) -> list[Finding]:
    if await project_repository.get_project(session, project_id) is None:
        raise ProjectNotFoundError("Project not found.")
    return await scan_repository.list_project_findings(
        session, project_id, severity=severity, limit=limit, offset=offset
    )


async def get_finding(session: AsyncSession, finding_id: uuid.UUID) -> FindingDetail | None:
    finding = await scan_repository.get_finding(session, finding_id)
    if finding is None:
        return None
    artifact = None
    if finding.artifact_id is not None:
        stored = await scan_repository.get_artifact(
            session, finding.test_run_id, finding.artifact_id
        )
        artifact = artifact_read(stored) if stored else None
    base = {
        name: getattr(finding, name)
        for name in FindingDetail.model_fields
        if name not in ("artifact",)
    }
    return FindingDetail(**base, artifact=artifact)


async def compare_scan(session: AsyncSession, run_id: uuid.UUID) -> RunComparison | None:
    run = await scan_repository.get_run(session, run_id)
    if run is None:
        return None
    previous = await scan_repository.previous_finished_run(session, run)
    current = await scan_repository.run_fingerprints(session, run_id)
    earlier = await scan_repository.run_fingerprints(session, previous.id) if previous else {}

    def item(finding: Finding) -> ComparisonFinding:
        return ComparisonFinding(
            fingerprint=finding.fingerprint,
            title=finding.title,
            severity=finding.severity,  # type: ignore[arg-type]
            affected_url=finding.affected_url,
            finding_id=finding.id,
        )

    return RunComparison(
        run_id=run.id,
        previous_run_id=previous.id if previous else None,
        new=[item(f) for key, f in current.items() if previous and key not in earlier],
        resolved=[item(f) for key, f in earlier.items() if key not in current],
        unchanged_count=len(current.keys() & earlier.keys()),
    )


async def artifact_file(
    session: AsyncSession, artifact_root: Path, run_id: uuid.UUID, artifact_id: uuid.UUID
) -> tuple[ScanArtifact, Path] | None:
    artifact = await scan_repository.get_artifact(session, run_id, artifact_id)
    if artifact is None:
        return None
    try:
        path = resolve_artifact_path(artifact_root, artifact.storage_key)
    except ArtifactPathError:
        logger.error("Artifact %s has an invalid storage key", artifact.id)
        return None
    if not path.is_file():
        return None  # removed by the retention policy
    return artifact, path


async def latest_scans(
    session: AsyncSession, project_ids: list[uuid.UUID]
) -> dict[uuid.UUID, LatestScan]:
    runs = await scan_repository.latest_runs_for_projects(session, project_ids)
    return {
        project_id: LatestScan(
            id=run.id,
            status=run.status,  # type: ignore[arg-type]
            created_at=run.created_at,
            finished_at=run.finished_at,
            findings_count=run.findings_count,
        )
        for project_id, run in runs.items()
    }


async def dashboard_summary(session: AsyncSession) -> DashboardSummary:
    latest = await scan_repository.latest_runs_for_projects(session, None, finished_only=True)
    return DashboardSummary(
        project_count=await project_repository.count_projects(session),
        scan_count=await scan_repository.count_runs(session),
        active_scan_count=await scan_repository.count_active(session),
        latest_findings_count=sum(run.findings_count for run in latest.values()),
    )
