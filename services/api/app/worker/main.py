"""Scan worker: claims queued runs, runs the isolated scanner, and records the outcome.

Lifecycle guarantees (single PostgreSQL database, any number of workers):
* A run is processed only by the worker whose atomic queued -> running claim succeeded.
* Results are written together with the terminal status in one transaction, and only while
  the run is still owned by the claiming attempt.
* A run never stays "running" forever: a heartbeat is refreshed while it is processed, and
  any worker re-queues (or, after SCAN_MAX_ATTEMPTS, fails) runs whose heartbeat stopped.
This is at-least-once execution with idempotent result storage, not exactly-once execution.
"""

import asyncio
import contextlib
import logging
import shutil
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.artifacts import cleanup_expired
from app.core.config import Settings
from app.repositories import scan as scan_repository
from app.scanner.contract import ScanJob
from app.services.scan import policy_config, scan_limits
from app.worker import executor
from app.worker.persistence import persist_result
from app.worker.queue import ScanQueue

logger = logging.getLogger("app.worker")

HEARTBEAT_SECONDS = 15
STALE_AFTER_SECONDS = 90
SWEEP_SECONDS = 30
CLEANUP_SECONDS = 3_600


def _now() -> datetime:
    return datetime.now(UTC)


class ScanWorker:
    def __init__(
        self,
        settings: Settings,
        session_factory: async_sessionmaker[AsyncSession],
        queue: ScanQueue,
    ) -> None:
        self.settings = settings
        self.sessions = session_factory
        self.queue = queue
        self._slots = asyncio.Semaphore(settings.worker_concurrency)
        self._tasks: dict[uuid.UUID, tuple[asyncio.Task[None], int]] = {}
        self._stopping = False

    async def run_forever(self) -> None:
        logger.info(
            "Worker started (queue=%s, concurrency=%d)",
            self.settings.queue_backend,
            self.settings.worker_concurrency,
        )
        await self.recover_stale_runs()
        last_sweep = last_cleanup = asyncio.get_running_loop().time()
        await self.cleanup_artifacts()
        try:
            while not self._stopping:
                await self._slots.acquire()
                started = False
                try:
                    started = await self._start_next()
                finally:
                    if not started:
                        self._slots.release()
                now = asyncio.get_running_loop().time()
                if now - last_sweep >= SWEEP_SECONDS:
                    await self.recover_stale_runs()
                    last_sweep = now
                if now - last_cleanup >= CLEANUP_SECONDS:
                    await self.cleanup_artifacts()
                    last_cleanup = now
        finally:
            await self.shutdown()

    async def _start_next(self) -> bool:
        """Wait briefly for work and start one run. Returns True if a run was started."""
        candidates: list[uuid.UUID] = []
        try:
            announced = await self.queue.dequeue(self.settings.worker_poll_interval_seconds)
        except Exception:  # noqa: BLE001 - the database sweep still finds queued work
            logger.warning("Queue unavailable; falling back to database polling")
            announced = None
            await asyncio.sleep(self.settings.worker_poll_interval_seconds)
        if announced is not None:
            candidates.append(announced)
        async with self.sessions() as session:
            candidates.extend(await scan_repository.queued_run_ids(session, limit=5))
        if not candidates and self.settings.queue_backend == "database":
            await asyncio.sleep(self.settings.worker_poll_interval_seconds)
        for run_id in dict.fromkeys(candidates):
            async with self.sessions() as session:
                attempt = await scan_repository.claim_run(session, run_id, _now())
            if attempt is None:
                continue  # already claimed, cancelled, or a duplicate message
            task = asyncio.create_task(self._process(run_id, attempt))
            self._tasks[run_id] = (task, attempt)
            return True
        return False

    async def _process(self, run_id: uuid.UUID, attempt: int) -> None:
        heartbeat = asyncio.create_task(self._heartbeat(run_id, attempt))
        work_dir = executor.job_output_dir(self.settings.artifact_dir, str(run_id), attempt)
        try:
            async with self.sessions() as session:
                run = await scan_repository.get_run(session, run_id)
            if run is None:
                return
            logger.info("Scanning run %s (attempt %d): %s", run_id, attempt, run.target_url)
            job = ScanJob(
                run_id=str(run_id),
                target_url=run.target_url,
                output_dir=str(work_dir),
                limits=scan_limits(self.settings, run.max_links),
                policy=policy_config(self.settings),
            )
            try:
                result = await executor.run_scanner(job)
            except Exception as error:  # noqa: BLE001 - any crash must end in a recorded state
                logger.exception("Scanner failed for run %s", run_id)
                await self._retry_or_fail(run_id, attempt, f"Scanner process failed: {error}")
                return
            async with self.sessions() as session:
                stored = await persist_result(
                    session,
                    run_id=run_id,
                    attempt=attempt,
                    result=result,
                    work_dir=work_dir,
                    artifact_root=self.settings.artifact_dir,
                    max_artifact_bytes=self.settings.artifact_max_bytes,
                )
            if stored:
                logger.info(
                    "Run %s finished: %s, %d finding(s)",
                    run_id,
                    result.outcome,
                    len(result.findings),
                )
            else:
                logger.warning("Run %s changed while scanning; result discarded", run_id)
        except Exception:  # noqa: BLE001
            logger.exception("Unexpected error while processing run %s", run_id)
            await self._retry_or_fail(run_id, attempt, "Unexpected worker error.")
        finally:
            heartbeat.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await heartbeat
            shutil.rmtree(work_dir, ignore_errors=True)
            self._tasks.pop(run_id, None)
            self._slots.release()

    async def _heartbeat(self, run_id: uuid.UUID, attempt: int) -> None:
        while True:
            await asyncio.sleep(HEARTBEAT_SECONDS)
            try:
                async with self.sessions() as session:
                    await scan_repository.touch_heartbeat(session, run_id, attempt, _now())
            except Exception:  # noqa: BLE001
                logger.warning("Heartbeat update failed for run %s", run_id)

    async def _retry_or_fail(self, run_id: uuid.UUID, attempt: int, reason: str) -> None:
        try:
            async with self.sessions() as session:
                if attempt < self.settings.scan_max_attempts:
                    requeued = await scan_repository.transition(
                        session,
                        run_id,
                        from_status="running",
                        attempt=attempt,
                        status="queued",
                        heartbeat_at=None,
                    )
                    if requeued:
                        logger.info("Run %s re-queued after attempt %d", run_id, attempt)
                        with contextlib.suppress(Exception):
                            await self.queue.enqueue(run_id)
                        return
                await scan_repository.transition(
                    session,
                    run_id,
                    from_status="running",
                    attempt=attempt,
                    status="failed",
                    failure_reason=reason[:500],
                    finished_at=_now(),
                )
        except Exception:  # noqa: BLE001 - the stale-run sweep is the last line of defence
            logger.exception("Could not record failure for run %s", run_id)

    async def recover_stale_runs(self) -> None:
        cutoff = _now() - timedelta(seconds=STALE_AFTER_SECONDS)
        try:
            async with self.sessions() as session:
                stale = await scan_repository.stale_running_runs(session, cutoff)
            for run in stale:
                if run.id in self._tasks:
                    continue
                logger.warning("Run %s stopped sending heartbeats", run.id)
                await self._retry_or_fail(
                    run.id, run.attempts, "The worker stopped before the scan finished."
                )
        except Exception:  # noqa: BLE001
            logger.exception("Stale run recovery failed")

    async def cleanup_artifacts(self) -> None:
        try:
            async with self.sessions() as session:
                known = await scan_repository.all_run_ids(session)
            await asyncio.to_thread(
                cleanup_expired,
                self.settings.artifact_dir,
                self.settings.artifact_retention_days,
                known,
            )
        except Exception:  # noqa: BLE001
            logger.exception("Artifact cleanup failed")

    async def shutdown(self) -> None:
        """Stop scanners and hand in-flight runs back to the queue for another attempt."""
        self._stopping = True
        in_flight = dict(self._tasks)
        if not in_flight:
            return
        logger.info("Stopping %d in-flight scan(s)", len(in_flight))
        executor.kill_all()
        for task, _attempt in in_flight.values():
            task.cancel()
        await asyncio.gather(*(task for task, _ in in_flight.values()), return_exceptions=True)
        async with self.sessions() as session:
            for run_id, (_task, attempt) in in_flight.items():
                with contextlib.suppress(Exception):
                    await scan_repository.transition(
                        session,
                        run_id,
                        from_status="running",
                        attempt=attempt,
                        status="queued",
                        heartbeat_at=None,
                    )
