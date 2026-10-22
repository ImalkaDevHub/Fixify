"""Scanner process entry point: ``python -m app.scanner`` reads a ScanJob on stdin and writes
a ScanResult on stdout.

The worker starts this process with a minimal environment (no database or Redis settings) and
kills its whole process tree if it exceeds the hard time limit.
"""

import asyncio
import logging
import sys

from app.scanner.contract import ScanJob
from app.scanner.engine import ScanEngine


def main() -> int:
    logging.basicConfig(level=logging.WARNING, stream=sys.stderr)
    job = ScanJob.model_validate_json(sys.stdin.buffer.read())
    result = asyncio.run(ScanEngine(job).run())
    # Raw UTF-8 bytes: sys.stdout uses the console code page on Windows (e.g. cp1252).
    sys.stdout.buffer.write(result.model_dump_json().encode("utf-8"))
    sys.stdout.buffer.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
