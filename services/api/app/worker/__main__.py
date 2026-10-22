"""Start the scan worker: ``python -m app.worker``."""

import asyncio
import sys

from app.core.config import settings
from app.core.logging import configure_logging
from app.db.session import SessionFactory, engine
from app.worker.main import ScanWorker
from app.worker.queue import create_queue


async def main() -> None:
    queue = create_queue(settings)
    try:
        await ScanWorker(settings, SessionFactory, queue).run_forever()
    finally:
        await queue.close()
        await engine.dispose()


if __name__ == "__main__":
    configure_logging()
    # psycopg's async mode needs a selector event loop on Windows.
    loop_factory = asyncio.SelectorEventLoop if sys.platform == "win32" else None
    try:
        asyncio.run(main(), loop_factory=loop_factory)
    except KeyboardInterrupt:
        pass
