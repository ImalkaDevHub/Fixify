"""Writes a scanner result to PostgreSQL in one transaction, idempotently."""

import logging
import uuid
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.artifacts import (
    ArtifactPathError,
    resolve_artifact_path,
    storage_key,
    store_file,
)
from app.db.models.scan import Finding, ScanArtifact, TestCaseResult, TestRun
from app.repositories import scan as scan_repository
from app.scanner.contract import ScanResult
from app.scanner.sanitize import clean_text

logger = logging.getLogger(__name__)


async def persist_result(
    session: AsyncSession,
    *,
    run_id: uuid.UUID,
    attempt: int,
    result: ScanResult,
    work_dir: Path,
    artifact_root: Path,
    max_artifact_bytes: int,
) -> bool:
    """Store results and move the run to its terminal state.

    Returns False (and stores nothing) if the run is no longer owned by this attempt, for
    example because it was deleted or recovered by another worker. Results from any earlier
    attempt are replaced, so retries and duplicate deliveries never duplicate findings.
    """
    run = await session.scalar(
        select(TestRun)
        .where(TestRun.id == run_id, TestRun.status == "running", TestRun.attempts == attempt)
        .with_for_update()
    )
    if run is None:
        await session.rollback()
        return False

    stale_files = [
        artifact.storage_key for artifact in await scan_repository.list_artifacts(session, run_id)
    ]
    await scan_repository.clear_results(session, run_id)

    artifact_ids: dict[str, uuid.UUID] = {}
    for artifact in result.artifacts:
        artifact_id = uuid.uuid4()
        key = storage_key(run_id, artifact_id)
        source = work_dir / Path(artifact.file_name).name  # never trust a path from the scanner
        try:
            size = store_file(artifact_root, source, key, max_artifact_bytes)
        except (ArtifactPathError, OSError) as error:
            logger.warning("Artifact %s for run %s not stored: %s", artifact.key, run_id, error)
            continue
        session.add(
            ScanArtifact(
                id=artifact_id,
                test_run_id=run_id,
                project_id=run.project_id,
                kind=artifact.kind,
                content_type=artifact.content_type,
                storage_key=key,
                size_bytes=size,
                width=artifact.width,
                height=artifact.height,
                sha256=artifact.sha256,
            )
        )
        artifact_ids[artifact.key] = artifact_id
    await session.flush()

    for check in result.checks:
        session.add(
            TestCaseResult(
                test_run_id=run_id,
                name=check.name,
                check_type=check.check_type,
                status=check.status,
                target_url=check.target_url[:2048],
                summary=check.summary[:500],
                started_at=check.started_at,
                finished_at=check.finished_at,
                duration_ms=check.duration_ms,
                details=check.details,
            )
        )

    now = datetime.now(UTC)
    earlier = await scan_repository.first_detected(
        session, run.project_id, [finding.fingerprint for finding in result.findings]
    )
    for finding in result.findings:
        session.add(
            Finding(
                test_run_id=run_id,
                project_id=run.project_id,
                check_type=finding.check_type,
                finding_type=finding.finding_type,
                title=finding.title[:200],
                description=finding.description,
                severity=finding.severity,
                confidence=finding.confidence,
                affected_url=finding.affected_url[:2048] if finding.affected_url else None,
                http_status=finding.http_status,
                evidence=finding.evidence,
                fingerprint=finding.fingerprint,
                artifact_id=artifact_ids.get(finding.artifact_key or ""),
                first_detected_at=earlier.get(finding.fingerprint, now),
            )
        )

    severities = Counter(finding.severity for finding in result.findings)
    run.status = result.outcome
    run.final_url = result.final_url[:2048] if result.final_url else None
    run.failure_reason = clean_text(result.failure_reason, 500) if result.failure_reason else None
    run.checks_total = len(result.checks)
    run.checks_passed = result.passed_count
    run.checks_failed = result.failed_count
    run.checks_errored = result.error_count
    run.checks_skipped = result.skipped_count
    run.findings_count = len(result.findings)
    run.critical_count = severities["critical"]
    run.high_count = severities["high"]
    run.medium_count = severities["medium"]
    run.low_count = severities["low"]
    run.info_count = severities["info"]
    run.finished_at = now
    await session.commit()

    # Files from an earlier attempt are removed only once the new rows are committed.
    for key in stale_files:
        try:
            resolve_artifact_path(artifact_root, key).unlink(missing_ok=True)
        except (ArtifactPathError, OSError):
            logger.warning("Could not remove stale artifact %s", key)
    return True
