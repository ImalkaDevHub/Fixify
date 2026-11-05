"""Background job worker for AI analysis, fix generation, and pull requests.

Same guarantees as the scan worker: an atomic queued -> running claim, a heartbeat, bounded
retries with backoff for transient errors, recovery of jobs whose worker died, and results
committed together with the terminal status (only by the attempt that owns the job).
"""

import asyncio
import contextlib
import logging
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.provider import AIProvider
from app.core.config import Settings
from app.db.models.platform import BackgroundJob
from app.services import analysis as analysis_service
from app.services import fixes as fix_service
from app.services import jobs as job_service
from app.services import notifications
from app.services.jobs import JobError

logger = logging.getLogger("app.worker.jobs")

Handler = Callable[[AsyncSession, BackgroundJob, AIProvider | None, Settings], Awaitable[uuid.UUID]]

HANDLERS: dict[str, Handler] = {
    "analyze_finding": analysis_service.run_analysis,
    "generate_fix": fix_service.run_fix_generation,
    "create_pull_request": fix_service.run_pull_request,
}
LABELS = {
    "analyze_finding": "AI analysis",
    "generate_fix": "Fix generation",
    "create_pull_request": "Pull request creation",
}
HEARTBEAT_SECONDS = 15
STALE_AFTER_SECONDS = 180
POLL_SECONDS = 2
# While the database is unreachable: wait 2 s, 4 s, ... up to 30 s between attempts.
OUTAGE_BACKOFF_START_SECONDS = 2
OUTAGE_BACKOFF_MAX_SECONDS = 30


def _now() -> datetime:
    return datetime.now(UTC)


def backoff(attempt: int) -> timedelta:
    return timedelta(seconds=min(600, 20 * 2 ** (attempt - 1)))


class JobWorker:
    def __init__(
        self,
        settings: Settings,
        session_factory: async_sessionmaker[AsyncSession],
        provider_factory: Callable[[], AIProvider | None],
    ) -> None:
        self.settings = settings
        self.sessions = session_factory
        self.provider_factory = provider_factory
        self._slots = asyncio.Semaphore(settings.job_concurrency)
        self._tasks: set[asyncio.Task[None]] = set()
        self._stopping = False

    async def run_forever(self) -> None:
        logger.info("Job worker started (concurrency=%d)", self.settings.job_concurrency)
        last_sweep = 0.0
        backoff = OUTAGE_BACKOFF_START_SECONDS
        try:
            while not self._stopping:
                loop_time = asyncio.get_running_loop().time()
                if loop_time - last_sweep >= 30:
                    await self.recover_stale()
                    last_sweep = loop_time
                try:
                    started = await self.start_due()
                except Exception as error:  # noqa: BLE001 - a database outage must not end the worker
                    logger.warning(
                        "Job polling failed (%s); retrying in %d s",
                        type(error).__name__,
                        backoff,
                    )
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, OUTAGE_BACKOFF_MAX_SECONDS)
                    continue
                backoff = OUTAGE_BACKOFF_START_SECONDS
                if not started:
                    await asyncio.sleep(POLL_SECONDS)
        finally:
            await self.shutdown()

    async def start_due(self) -> int:
        """Claim and start as many due jobs as there are free slots."""
        started = 0
        async with self.sessions() as session:
            due = await job_service.due_job_ids(session, _now(), limit=10)
        for job_id in due:
            if self._slots.locked():
                break
            async with self.sessions() as session:
                attempt = await job_service.claim(session, job_id, _now())
            if attempt is None:
                continue
            await self._slots.acquire()
            task = asyncio.create_task(self._run(job_id, attempt))
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)
            started += 1
        return started

    async def drain(self) -> None:
        """Process every due job and wait for completion (tests and one-shot runs)."""
        while await self.start_due():
            await asyncio.gather(*list(self._tasks), return_exceptions=True)
        await asyncio.gather(*list(self._tasks), return_exceptions=True)

    async def _run(self, job_id: uuid.UUID, attempt: int) -> None:
        heartbeat = asyncio.create_task(self._heartbeat(job_id, attempt))
        try:
            await self._process(job_id, attempt)
        finally:
            heartbeat.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await heartbeat
            self._slots.release()

    async def _process(self, job_id: uuid.UUID, attempt: int) -> None:
        async with self.sessions() as session:
            job = await session.get(BackgroundJob, job_id)
            if job is None:
                return
            handler = HANDLERS.get(job.kind)
            logger.info("Running job %s (%s, attempt %d)", job_id, job.kind, attempt)
            try:
                if handler is None:
                    raise JobError(f"Unknown job type {job.kind!r}.")
                result_id = await handler(session, job, self.provider_factory(), self.settings)
            except JobError as error:
                await session.rollback()
                await self._failed(job_id, attempt, error.public_message, error.retryable)
                return
            except Exception:  # noqa: BLE001 - every crash must end in a recorded state
                logger.exception("Job %s crashed", job_id)
                await session.rollback()
                await self._failed(job_id, attempt, "Unexpected error while processing.", True)
                return
            done = await job_service.transition(
                session,
                job_id,
                attempt,
                status="succeeded",
                result_id=result_id,
                finished_at=_now(),
                error=None,
            )
            if done:
                await session.commit()  # result and status in one transaction
                logger.info("Job %s succeeded", job_id)
            else:
                await session.rollback()
                logger.warning("Job %s changed while running; result discarded", job_id)

    async def _failed(self, job_id: uuid.UUID, attempt: int, message: str, retryable: bool) -> None:
        async with self.sessions() as session:
            job = await session.get(BackgroundJob, job_id)
            if job is None:
                return
            if retryable and attempt < job.max_attempts:
                if await job_service.transition(
                    session,
                    job_id,
                    attempt,
                    status="queued",
                    error=message[:500],
                    run_after=_now() + backoff(attempt),
                    heartbeat_at=None,
                ):
                    await session.commit()
                    logger.info("Job %s will retry: %s", job_id, message)
                return
            if not await job_service.transition(
                session, job_id, attempt, status="failed", error=message[:500], finished_at=_now()
            ):
                await session.rollback()
                return
            if job.kind == "create_pull_request":
                pr = await fix_service.pull_request_for(session, job.subject_id)
                if pr is not None and pr.status == "creating":
                    pr.status, pr.error = "failed", message[:500]
            await notifications.notify(
                session,
                user_id=job.owner_id,
                kind="job_failed",
                title=f"{LABELS.get(job.kind, 'Background work')} failed",
                body=message,
                link=_link_for(job),
                project_id=job.project_id,
                dedupe_key=f"job-failed:{job.id}",
            )
            await session.commit()
            logger.warning("Job %s failed: %s", job_id, message)

    async def _heartbeat(self, job_id: uuid.UUID, attempt: int) -> None:
        while True:
            await asyncio.sleep(HEARTBEAT_SECONDS)
            try:
                async with self.sessions() as session:
                    await job_service.touch(session, job_id, attempt)
            except Exception:  # noqa: BLE001
                logger.warning("Heartbeat failed for job %s", job_id)

    async def recover_stale(self) -> None:
        try:
            async with self.sessions() as session:
                stale = await job_service.stale_jobs(
                    session, _now() - timedelta(seconds=STALE_AFTER_SECONDS)
                )
            for job in stale:
                await self._failed(
                    job.id, job.attempts, "The worker stopped before finishing.", True
                )
        except Exception:  # noqa: BLE001
            logger.exception("Stale job recovery failed")

    async def shutdown(self) -> None:
        self._stopping = True
        for task in list(self._tasks):
            task.cancel()
        await asyncio.gather(*list(self._tasks), return_exceptions=True)


def _link_for(job: BackgroundJob) -> str:
    if job.kind == "create_pull_request":
        return f"/fixes/{job.subject_id}"
    return f"/findings/{job.subject_id}"
