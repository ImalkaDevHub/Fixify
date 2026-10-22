"""Runs the scanner in a separate process with a minimal environment and a hard time limit."""

import asyncio
import logging
import os
import signal
import subprocess
import sys
from pathlib import Path

from app.core.config import API_ROOT
from app.scanner.contract import ScanJob, ScanResult

logger = logging.getLogger(__name__)

# Variables the scanner process may inherit. Database URLs, Redis URLs, and every other
# application setting are deliberately excluded.
_SCANNER_ENV_KEYS = (
    "PATH",
    "SYSTEMROOT",
    "SystemRoot",
    "WINDIR",
    "TEMP",
    "TMP",
    "HOME",
    "USERPROFILE",
    "LOCALAPPDATA",
    "APPDATA",
    "LANG",
    "TZ",
    "PLAYWRIGHT_BROWSERS_PATH",
    "VIRTUAL_ENV",
)
_GRACE_SECONDS = 30
_MAX_OUTPUT_BYTES = 10_000_000
_active: set[subprocess.Popen[bytes]] = set()


class ScannerProcessError(RuntimeError):
    """The scanner process crashed, timed out, or produced no valid result."""


def scanner_env() -> dict[str, str]:
    env = {key: os.environ[key] for key in _SCANNER_ENV_KEYS if key in os.environ}
    env["PYTHONUNBUFFERED"] = "1"
    return env


def _kill_tree(process: subprocess.Popen[bytes]) -> None:
    """Kill the scanner and every Chromium process it started."""
    if sys.platform == "win32":
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(process.pid)],
            capture_output=True,
            check=False,
        )
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    process.kill()


def _run_blocking(job: ScanJob, hard_timeout: float) -> ScanResult:
    kwargs: dict[str, object] = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True  # its own process group, so killpg reaches Chromium
    process = subprocess.Popen(
        [sys.executable, "-m", "app.scanner"],
        cwd=API_ROOT,
        env=scanner_env(),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        **kwargs,  # type: ignore[arg-type]
    )
    _active.add(process)
    try:
        stdout, stderr = process.communicate(job.model_dump_json().encode(), timeout=hard_timeout)
    except subprocess.TimeoutExpired as error:
        _kill_tree(process)
        process.communicate()
        raise ScannerProcessError("The scanner exceeded its hard time limit.") from error
    finally:
        _active.discard(process)
        if process.poll() is None:
            _kill_tree(process)
    if stderr:
        logger.info("Scanner stderr: %s", stderr.decode(errors="replace")[-2_000:])
    if process.returncode != 0:
        raise ScannerProcessError(f"The scanner exited with code {process.returncode}.")
    if len(stdout) > _MAX_OUTPUT_BYTES:
        raise ScannerProcessError("The scanner produced an oversized result.")
    try:
        return ScanResult.model_validate_json(stdout)
    except ValueError as error:
        raise ScannerProcessError("The scanner produced an invalid result.") from error


def kill_all() -> None:
    """Stop every running scanner (used on worker shutdown)."""
    for process in list(_active):
        if process.poll() is None:
            _kill_tree(process)


async def run_scanner(job: ScanJob) -> ScanResult:
    hard_timeout = job.limits.max_scan_duration_seconds + _GRACE_SECONDS
    # A thread keeps this independent of the event loop type (psycopg needs a selector loop on
    # Windows, which cannot run asyncio subprocesses).
    return await asyncio.to_thread(_run_blocking, job, hard_timeout)


def job_output_dir(root: Path, run_id: str, attempt: int) -> Path:
    return root / ".work" / f"{run_id}-{attempt}"
