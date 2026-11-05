"""Start the worker: ``python -m app.worker``.

One process runs the scan worker, the background job worker (AI analysis, fixes, pull
requests), and the scan scheduler. Each loop is independent; one failing never stops another.

Shutdown: SIGINT (Ctrl+C), SIGTERM (``docker stop``, process managers) and, on Windows,
Ctrl+Break all cancel the main task, so each loop's ``shutdown()`` runs: scanners are stopped
and in-flight scans and jobs are handed back to the queue instead of waiting for stale-run
recovery.
"""

import asyncio
import contextlib
import logging
import signal
import sys

from app.ai.provider import get_ai_provider
from app.core.config import settings
from app.core.logging import configure_logging
from app.db.session import SessionFactory, engine
from app.worker.jobs import JobWorker
from app.worker.main import ScanWorker
from app.worker.queue import create_queue
from app.worker.scheduler import Scheduler

logger = logging.getLogger("app.worker")


async def main() -> None:
    queue = create_queue(settings)
    scheduler_queue = create_queue(settings)  # separate connection: dequeue blocks the other
    try:
        await asyncio.gather(
            ScanWorker(settings, SessionFactory, queue).run_forever(),
            JobWorker(settings, SessionFactory, get_ai_provider).run_forever(),
            Scheduler(settings, SessionFactory, scheduler_queue).run_forever(),
        )
    finally:
        await queue.close()
        await scheduler_queue.close()
        await engine.dispose()


def _install_shutdown_handlers(loop: asyncio.AbstractEventLoop, task: asyncio.Task[None]) -> None:
    """Cancel ``task`` on a termination signal. Works with the Windows selector loop, which
    has no ``loop.add_signal_handler``."""

    def request_stop(signum: int, _frame: object) -> None:
        logger.info("Received %s; shutting down", signal.Signals(signum).name)
        loop.call_soon_threadsafe(task.cancel)

    for name in ("SIGINT", "SIGTERM", "SIGBREAK"):
        if hasattr(signal, name):
            with contextlib.suppress(OSError, ValueError):
                signal.signal(getattr(signal, name), request_stop)


async def run() -> None:
    task = asyncio.ensure_future(main())
    _install_shutdown_handlers(asyncio.get_running_loop(), task)
    with contextlib.suppress(asyncio.CancelledError):
        await task
    logger.info("Worker stopped")


if __name__ == "__main__":
    configure_logging()
    # psycopg's async mode needs a selector event loop on Windows.
    loop_factory = asyncio.SelectorEventLoop if sys.platform == "win32" else None
    try:
        asyncio.run(run(), loop_factory=loop_factory)
    except KeyboardInterrupt:
        pass
