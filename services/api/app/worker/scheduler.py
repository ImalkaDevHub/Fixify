"""Scan scheduler loop (runs inside the worker process)."""

import asyncio
import logging

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.services.schedules import run_due_schedules
from app.worker.queue import ScanQueue

logger = logging.getLogger("app.worker.scheduler")


class Scheduler:
    def __init__(
        self,
        settings: Settings,
        session_factory: async_sessionmaker[AsyncSession],
        queue: ScanQueue,
    ) -> None:
        self.settings = settings
        self.sessions = session_factory
        self.queue = queue

    async def run_forever(self) -> None:
        logger.info("Scheduler started (every %d s)", self.settings.scheduler_interval_seconds)
        while True:
            try:
                await run_due_schedules(self.sessions, self.queue, self.settings)
            except Exception:  # noqa: BLE001 - the next tick tries again
                logger.exception("Scheduler tick failed")
            await asyncio.sleep(self.settings.scheduler_interval_seconds)
