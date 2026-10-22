"""Scan lifecycle: claiming, retries, stale-run recovery, and idempotent result storage."""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.core.config import Settings
from app.db.models import Finding, Project, TestRun
from app.repositories import scan as scan_repository
from app.worker import executor
from app.worker import main as worker_main
from app.worker.main import ScanWorker
from app.worker.persistence import persist_result
from tests.conftest import FakeQueue
from tests.scan_helpers import PNG, finding, scan_result


@pytest.fixture
def worker_settings(tmp_path):
    return Settings(
        artifact_dir=tmp_path / "artifacts",
        queue_backend="database",
        worker_poll_interval_seconds=1,
        scan_max_attempts=2,
    )


async def _queued_run(session_factory) -> uuid.UUID:
    async with session_factory() as session:
        project = Project(name="Site", website_url="https://example.com/")
        session.add(project)
        await session.commit()
        run = await scan_repository.create_run(
            session, project_id=project.id, target_url=project.website_url, max_links=5
        )
        return run.id


async def _status(session_factory, run_id: uuid.UUID) -> TestRun:
    async with session_factory() as session:
        run = await scan_repository.get_run(session, run_id)
        assert run is not None
        return run


async def test_claim_is_atomic_and_duplicate_delivery_is_ignored(session_factory):
    run_id = await _queued_run(session_factory)
    now = datetime.now(UTC)
    async with session_factory() as session:
        first = await scan_repository.claim_run(session, run_id, now)
    async with session_factory() as session:
        second = await scan_repository.claim_run(session, run_id, now)
    assert (first, second) == (1, None)
    assert (await _status(session_factory, run_id)).status == "running"


async def _drain(worker: ScanWorker) -> None:
    """Start one run and wait for it to finish."""
    await worker._slots.acquire()
    assert await worker._start_next()
    await asyncio.gather(*(task for task, _ in list(worker._tasks.values())))


async def test_worker_runs_scanner_and_stores_results(
    session_factory, worker_settings, monkeypatch
):
    run_id = await _queued_run(session_factory)
    seen_jobs = []

    async def fake_scanner(job):
        seen_jobs.append(job)
        output = worker_settings.artifact_dir / ".work"
        assert job.output_dir.startswith(str(output))
        from pathlib import Path

        Path(job.output_dir).mkdir(parents=True, exist_ok=True)
        (Path(job.output_dir) / "screenshot.png").write_bytes(PNG)
        return scan_result([finding("a", "high", artifact_key="screenshot")])

    monkeypatch.setattr(executor, "run_scanner", fake_scanner)
    worker = ScanWorker(worker_settings, session_factory, FakeQueue())
    await _drain(worker)

    run = await _status(session_factory, run_id)
    assert run.status == "completed"
    assert (run.findings_count, run.high_count, run.checks_total) == (1, 1, 2)
    assert run.finished_at is not None
    assert seen_jobs[0].limits.max_links == 5
    assert not (worker_settings.artifact_dir / ".work").exists() or not any(
        (worker_settings.artifact_dir / ".work").iterdir()
    )
    stored = list((worker_settings.artifact_dir / str(run_id)).glob("*.png"))
    assert len(stored) == 1


async def test_scanner_crash_is_retried_then_failed(session_factory, worker_settings, monkeypatch):
    run_id = await _queued_run(session_factory)
    calls = 0

    async def crashing_scanner(_job):
        nonlocal calls
        calls += 1
        raise executor.ScannerProcessError("The scanner exited with code 1.")

    monkeypatch.setattr(executor, "run_scanner", crashing_scanner)
    worker = ScanWorker(worker_settings, session_factory, FakeQueue())

    await _drain(worker)
    run = await _status(session_factory, run_id)
    assert (run.status, run.attempts) == ("queued", 1)  # bounded retry

    await _drain(worker)
    run = await _status(session_factory, run_id)
    assert (run.status, run.attempts) == ("failed", 2)
    assert "Scanner process failed" in (run.failure_reason or "")
    assert calls == 2
    assert worker._slots._value == worker_settings.worker_concurrency  # slots released


async def test_stale_running_run_is_recovered(session_factory, worker_settings):
    run_id = await _queued_run(session_factory)
    long_ago = datetime.now(UTC) - timedelta(minutes=10)
    async with session_factory() as session:
        await scan_repository.claim_run(session, run_id, long_ago)

    worker = ScanWorker(worker_settings, session_factory, FakeQueue())
    await worker.recover_stale_runs()
    run = await _status(session_factory, run_id)
    assert run.status == "queued"  # attempt 1 of 2: retried

    async with session_factory() as session:
        await scan_repository.claim_run(session, run_id, long_ago)
    await worker.recover_stale_runs()
    run = await _status(session_factory, run_id)
    assert run.status == "failed"
    assert run.failure_reason == "The worker stopped before the scan finished."


async def test_fresh_heartbeat_is_not_treated_as_stale(session_factory, worker_settings):
    run_id = await _queued_run(session_factory)
    async with session_factory() as session:
        await scan_repository.claim_run(session, run_id, datetime.now(UTC))
    await ScanWorker(worker_settings, session_factory, FakeQueue()).recover_stale_runs()
    assert (await _status(session_factory, run_id)).status == "running"


async def test_retry_replaces_results_instead_of_duplicating(session_factory, tmp_path):
    run_id = await _queued_run(session_factory)
    work = tmp_path / "work"
    work.mkdir()
    (work / "screenshot.png").write_bytes(PNG)
    root = tmp_path / "artifacts"
    result = scan_result([finding("a"), finding("b")])
    now = datetime.now(UTC)

    for _attempt in range(2):
        async with session_factory() as session:
            await scan_repository.transition(
                session, run_id, from_status="completed", status="queued"
            )
            attempt = await scan_repository.claim_run(session, run_id, now)
        async with session_factory() as session:
            assert await persist_result(
                session, run_id=run_id, attempt=attempt, result=result, work_dir=work,
                artifact_root=root, max_artifact_bytes=10_000,
            )

    async with session_factory() as session:
        count = await session.scalar(
            select(func.count()).select_from(Finding).where(Finding.test_run_id == run_id)
        )
    assert count == 2
    assert len(list((root / str(run_id)).glob("*.png"))) == 1  # old attempt's file removed


async def test_result_from_a_superseded_attempt_is_discarded(session_factory, tmp_path):
    run_id = await _queued_run(session_factory)
    async with session_factory() as session:
        attempt = await scan_repository.claim_run(session, run_id, datetime.now(UTC))
        # Another worker recovered the run and claimed attempt 2 meanwhile.
        await scan_repository.transition(session, run_id, from_status="running", status="queued")
        await scan_repository.claim_run(session, run_id, datetime.now(UTC))
    async with session_factory() as session:
        stored = await persist_result(
            session, run_id=run_id, attempt=attempt, result=scan_result([finding("late")]),
            work_dir=tmp_path, artifact_root=tmp_path / "a", max_artifact_bytes=10_000,
        )
    assert stored is False
    assert (await _status(session_factory, run_id)).findings_count == 0


async def test_cancelled_run_is_never_claimed(session_factory, worker_settings, monkeypatch):
    run_id = await _queued_run(session_factory)
    async with session_factory() as session:
        await scan_repository.transition(
            session, run_id, from_status="queued", status="cancelled"
        )
    monkeypatch.setattr(executor, "run_scanner", None)  # would crash if called
    worker = ScanWorker(worker_settings, session_factory, FakeQueue())
    await worker._slots.acquire()
    assert not await worker._start_next()


def test_scanner_environment_excludes_application_secrets(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:secret@db/x")
    monkeypatch.setenv("REDIS_URL", "redis://:secret@redis/0")
    monkeypatch.setenv("SOME_API_KEY", "secret")
    env = executor.scanner_env()
    assert "DATABASE_URL" not in env and "REDIS_URL" not in env and "SOME_API_KEY" not in env
    assert all("secret" not in value for value in env.values())


def test_stale_threshold_exceeds_heartbeat_interval():
    assert worker_main.STALE_AFTER_SECONDS >= 3 * worker_main.HEARTBEAT_SECONDS
