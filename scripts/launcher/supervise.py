"""Supervise one Fixify service for the launcher.

    python supervise.py --name api --cwd DIR --log FILE --runtime DIR -- <command...>

Starts the command in its own process group, appends its output to the log file, and records
the child's PID and identity in ``<runtime>/<name>.child.json``. It stops the service when:

* ``<runtime>/<name>.stop`` appears (written by ``fixify stop``), or
* the supervisor itself receives SIGTERM / SIGINT (POSIX) or Ctrl+Break (Windows).

Stopping is graceful first (Ctrl+Break / SIGINT to the service's process group), then forced
(process-tree kill) after the grace period. The supervisor exits with the service's exit code.
"""

from __future__ import annotations

import argparse
import json
import signal
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import proc  # noqa: E402

_stop_requested = False


def _request_stop(signum, frame) -> None:  # noqa: ARG001
    global _stop_requested
    _stop_requested = True


def _stamp() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", required=True)
    parser.add_argument("--cwd", required=True)
    parser.add_argument("--log", required=True)
    parser.add_argument("--runtime", required=True)
    parser.add_argument("--grace", type=float, default=15.0)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("no command given")

    runtime = Path(args.runtime)
    stop_file = runtime / f"{args.name}.stop"
    child_file = runtime / f"{args.name}.child.json"
    stop_file.unlink(missing_ok=True)

    for name in ("SIGTERM", "SIGINT", "SIGBREAK", "SIGHUP"):
        if hasattr(signal, name):
            try:
                signal.signal(getattr(signal, name), _request_stop)
            except (OSError, ValueError):
                pass

    log = open(args.log, "ab", buffering=0)  # noqa: SIM115 - closed in finally
    try:
        log.write(f"\n===== fixify launcher: starting {args.name} at {_stamp()} =====\n".encode())
        try:
            child = subprocess.Popen(
                command,
                cwd=args.cwd,
                stdout=log,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                **proc.popen_flags(),
            )
        except OSError as error:
            log.write(f"fixify launcher: could not start {command[0]!r}: {error}\n".encode())
            return 127

        child_identity = proc.identity(child.pid)
        child_file.write_text(json.dumps({"pid": child.pid, "identity": child_identity}))

        reason = "exited"
        while True:
            code = child.poll()
            if code is not None:
                break
            if _stop_requested or stop_file.exists():
                reason = "stopped by launcher"
                proc.request_graceful_stop(child.pid)
                deadline = time.monotonic() + args.grace
                while child.poll() is None and time.monotonic() < deadline:
                    time.sleep(0.2)
                if child.poll() is None:
                    reason = "force-stopped after grace period"
                    proc.kill_tree(child.pid)
                    try:
                        child.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        pass
                code = child.poll()
                break
            time.sleep(0.5)

        # No kill after the child has exited: its PID may already belong to another process.
        # Grandchildren share the child's process group and console, so Ctrl+Break / SIGINT
        # reaches them too; the force path kills the whole tree while the child is alive.
        footer = (
            f"===== fixify launcher: {args.name} {reason} (exit code {code}) at {_stamp()} ====="
        )
        log.write(f"{footer}\n".encode())
        return code if isinstance(code, int) and code >= 0 else 1
    finally:
        child_file.unlink(missing_ok=True)
        stop_file.unlink(missing_ok=True)
        log.close()


if __name__ == "__main__":
    sys.exit(main())
