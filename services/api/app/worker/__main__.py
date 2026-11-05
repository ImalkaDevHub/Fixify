"""Start the worker: ``python -m app.worker``.

One process runs the scan worker, the background job worker (AI analysis, fixes, pull
requests), and the scan scheduler. Each loop is independent; one failing never stops another.
"""

import asyncio
import sys

from app.ai.provider import get_ai_provider
from app.core.config import settings
from app.core.logging import configure_logging
from app.db.session import SessionFactory, engine
from app.worker.jobs import JobWorker
from app.worker.main import ScanWorker
from app.worker.queue import create_queue
from app.worker.scheduler import Scheduler


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


if __name__ == "__main__":
    configure_logging()
    # psycopg's async mode needs a selector event loop on Windows.
    loop_factory = asyncio.SelectorEventLoop if sys.platform == "win32" else None
    try:
        asyncio.run(main(), loop_factory=loop_factory)
    except KeyboardInterrupt:
        pass
