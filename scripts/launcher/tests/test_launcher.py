"""Tests for the Fixify launcher (standard library only).

    python -m unittest discover -s scripts/launcher/tests -v      (from the repository root)

Real processes are started (tiny Python dummies), supervised, detected as already running,
stopped gracefully or forcefully, and their state files cleaned up. Runtime and log
directories are redirected to a temporary folder; the real runtime/ and logs/ are not touched.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
import warnings
from pathlib import Path

HERE = Path(__file__).resolve().parent
LAUNCHER = HERE.parent
sys.path.insert(0, str(LAUNCHER))

import fixify  # noqa: E402
import proc  # noqa: E402

PY = sys.executable


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _run_launcher(
    args: list[str], root: Path, extra_env: dict | None = None, stdin: str = ""
) -> subprocess.CompletedProcess:
    env = dict(
        os.environ,
        FIXIFY_ROOT=str(root),
        NO_COLOR="1",
        PYTHONIOENCODING="utf-8",
        FIXIFY_NONINTERACTIVE="" if stdin else "1",
    )
    env.update(extra_env or {})
    return subprocess.run(
        [PY, str(LAUNCHER / "fixify.py"), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        input=stdin,
        timeout=180,
    )


class TempDirs(unittest.TestCase):
    def setUp(self) -> None:
        # Supervisors are detached on purpose; their Popen handles outlive the call.
        warnings.simplefilter("ignore", ResourceWarning)
        self.tmp = Path(tempfile.mkdtemp(prefix="fixify-launcher-test-"))
        self._saved = (fixify.RUNTIME, fixify.LOGS)
        fixify.RUNTIME = self.tmp / "runtime"
        fixify.LOGS = self.tmp / "logs"
        fixify.RUNTIME.mkdir()
        fixify.LOGS.mkdir()

    def tearDown(self) -> None:
        for name in ("worker", "api", "web"):
            if fixify.state_path(name).exists():
                fixify.stop_service(name, name, grace=5)
        fixify.RUNTIME, fixify.LOGS = self._saved


# ------------------------------------------------------------------------------------------
# Pure functions
# ------------------------------------------------------------------------------------------


class ParsingTests(unittest.TestCase):
    def test_dotenv(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".env", delete=False, encoding="utf-8") as f:
            f.write(
                textwrap.dedent("""\
                # comment
                A=1
                export B = two
                C="quoted # not a comment"
                D='single'
                E=value # trailing comment
                EMPTY=
                bad line
                1BAD=x
            """)
            )
        values = fixify.parse_dotenv(Path(f.name))
        os.unlink(f.name)
        self.assertEqual(
            values,
            {
                "A": "1",
                "B": "two",
                "C": "quoted # not a comment",
                "D": "single",
                "E": "value",
                "EMPTY": "",
            },
        )

    def test_ports_and_urls(self) -> None:
        saved = {
            k: os.environ.pop(k, None) for k in ("PORT", "API_PORT", "API_HOST", "PUBLIC_APP_URL")
        }
        try:
            config = fixify.Config({"PUBLIC_APP_URL": "http://localhost:3200/"})
            self.assertEqual(config.web_port, 3200)
            self.assertEqual(config.web_url, "http://localhost:3200")
            self.assertEqual(config.api_url, "http://127.0.0.1:8000")
            config = fixify.Config(
                {
                    "PUBLIC_APP_URL": "https://fixify.example.com",
                    "API_HOST": "0.0.0.0",
                    "API_PORT": "9000",
                }
            )
            self.assertEqual(config.web_port, 3000)
            self.assertEqual(config.api_url, "http://127.0.0.1:9000")
            os.environ["PORT"] = (
                "3100"  # process environment wins over .env, like pydantic-settings
            )
            self.assertEqual(fixify.Config({"PORT": "1"}).web_port, 3100)
        finally:
            os.environ.pop("PORT", None)
            for key, value in saved.items():
                if value is not None:
                    os.environ[key] = value

    def test_infra_needs(self) -> None:
        DEFAULT_PORTS = {"postgres": 5432, "redis": 6379}  # noqa: N806
        local_pg = {
            "database": {"local": True, "scheme": "postgresql", "port": 5432},
            "redis": {"local": True, "port": 6379},
            "redis_needed": True,
        }
        self.assertEqual(
            fixify.infra_needs(local_pg, DEFAULT_PORTS), {"postgres": True, "redis": True}
        )
        remote = {
            "database": {"local": False, "scheme": "postgresql", "port": 5432},
            "redis": {"local": True, "port": 6379},
            "redis_needed": False,
        }
        self.assertEqual(
            fixify.infra_needs(remote, DEFAULT_PORTS), {"postgres": False, "redis": False}
        )
        other_port = {
            "database": {"local": True, "scheme": "postgresql", "port": 5433},
            "redis": {"local": True, "port": 1},
            "redis_needed": True,
        }
        self.assertEqual(
            fixify.infra_needs(other_port, DEFAULT_PORTS), {"postgres": False, "redis": False}
        )
        # POSTGRES_HOST_PORT=5433 (native PostgreSQL on 5432): the container is on 5433.
        moved = {"postgres": 5433, "redis": 6379}
        local_5433 = dict(local_pg, database={"local": True, "scheme": "postgresql", "port": 5433})
        self.assertEqual(fixify.infra_needs(local_5433, moved)["postgres"], True)
        self.assertEqual(fixify.infra_needs(local_pg, moved)["postgres"], False)

    def test_worker_ready(self) -> None:
        line = '{"level": "INFO", "message": "%s"}'
        self.assertIsNone(fixify.worker_ready(line % "Worker started")[0])
        ok = "\n".join(line % m for m in fixify.WORKER_MARKERS)
        self.assertTrue(fixify.worker_ready(ok)[0])
        failed = ok + '\n{"level": "ERROR", "message": "Scheduler tick failed"}'
        ready, detail = fixify.worker_ready(failed)
        self.assertFalse(ready)
        self.assertIn("Scheduler tick failed", detail)
        self.assertFalse(fixify.worker_ready("Traceback (most recent call last):")[0])

    def test_strip_ansi(self) -> None:
        self.assertEqual(fixify.strip_ansi("\x1b[?25h\x1b[32mok\x1b[0m"), "ok")


class ProcessIdentityTests(unittest.TestCase):
    def test_own_process(self) -> None:
        me = proc.identity(os.getpid())
        self.assertTrue(me)
        self.assertTrue(proc.is_ours(os.getpid(), me))

    def test_reused_pid_is_not_ours(self) -> None:
        # Same PID, different creation time: what a reused PID looks like.
        self.assertFalse(proc.is_ours(os.getpid(), "not-the-recorded-identity"))

    def test_dead_process(self) -> None:
        child = subprocess.Popen([PY, "-c", "pass"])
        identity = proc.identity(child.pid)
        child.wait()
        time.sleep(0.2)
        self.assertFalse(proc.is_ours(child.pid, identity))
        self.assertFalse(proc.is_ours(None, None))


# ------------------------------------------------------------------------------------------
# Supervisor and service lifecycle (real processes)
# ------------------------------------------------------------------------------------------

GRACEFUL_CHILD = textwrap.dedent("""
    import signal, sys, time
    def bye(*_):
        print("graceful shutdown", flush=True)
        sys.exit(0)
    for name in ("SIGINT", "SIGTERM", "SIGBREAK"):
        if hasattr(signal, name):
            signal.signal(getattr(signal, name), bye)
    for marker in ("Worker started", "Job worker started", "Scheduler started"):
        print('{"level": "INFO", "message": "%s"}' % marker, flush=True)
    while True:
        time.sleep(0.2)
""")

STUBBORN_CHILD = textwrap.dedent("""
    import signal, time
    for name in ("SIGINT", "SIGTERM", "SIGBREAK"):
        if hasattr(signal, name):
            signal.signal(getattr(signal, name), signal.SIG_IGN)
    for marker in ("Worker started", "Job worker started", "Scheduler started"):
        print('{"level": "INFO", "message": "%s"}' % marker, flush=True)
    while True:
        time.sleep(0.2)
""")

CRASHING_CHILD = 'print("boom", flush=True); raise SystemExit(3)'


class LifecycleTests(TempDirs):
    def _spec(self, code: str, timeout: float = 30) -> fixify.ServiceSpec:
        return fixify.ServiceSpec(
            "worker",
            "Dummy worker",
            self.tmp,
            [PY, "-u", "-c", code],
            dict(os.environ, PYTHONUNBUFFERED="1"),
            timeout,
        )

    def test_start_detect_duplicate_and_graceful_stop(self) -> None:
        config = fixify.Config({})
        self.assertTrue(fixify.start_service(self._spec(GRACEFUL_CHILD), config))
        state = fixify.service_state("worker")
        self.assertTrue(state.running)
        self.assertTrue(
            proc.is_ours(state.pid, json.loads(fixify.state_path("worker").read_text())["identity"])
        )
        # Second start: detected, nothing new launched.
        self.assertFalse(fixify.start_service(self._spec(GRACEFUL_CHILD), config))
        self.assertTrue(fixify.stop_service("worker", "Dummy worker"))
        self.assertFalse(fixify.service_state("worker").running)
        self.assertFalse(any(fixify.RUNTIME.iterdir()), "runtime files left behind")
        log = (fixify.LOGS / "worker.log").read_text(encoding="utf-8")
        self.assertIn("graceful shutdown", log)
        self.assertIn("worker stopped by launcher", log)

    def test_force_stop_after_grace_period(self) -> None:
        # The child ignores the shutdown signal; the supervisor force-kills it after
        # its grace period.
        self.assertTrue(fixify.start_service(self._spec(STUBBORN_CHILD), fixify.Config({})))
        started = time.monotonic()
        self.assertTrue(fixify.stop_service("worker", "Dummy worker", grace=40))
        self.assertLess(time.monotonic() - started, 40)
        self.assertFalse(fixify.service_state("worker").running)
        self.assertIn(
            "force-stopped after grace period",
            (fixify.LOGS / "worker.log").read_text(encoding="utf-8"),
        )

    def test_crash_during_startup_is_reported(self) -> None:
        with self.assertRaises(fixify.StartError) as raised:
            fixify.start_service(self._spec(CRASHING_CHILD), fixify.Config({}))
        self.assertIn("exited during startup", str(raised.exception))
        self.assertIn("boom", str(raised.exception))

    def test_stale_state_is_cleared(self) -> None:
        dead = subprocess.Popen([PY, "-c", "pass"])
        identity = proc.identity(dead.pid)
        dead.wait()
        fixify.state_path("api").write_text(json.dumps({"pid": dead.pid, "identity": identity}))
        (fixify.RUNTIME / "api.child.json").write_text(
            json.dumps({"pid": os.getpid(), "identity": "reused"})
        )
        state = fixify.service_state("api")
        self.assertFalse(state.running)
        self.assertTrue(state.stale_cleared)
        self.assertFalse(fixify.state_path("api").exists())
        self.assertFalse((fixify.RUNTIME / "api.child.json").exists())

    def test_stop_never_touches_unrelated_pid(self) -> None:
        # A state file pointing at this test process with a wrong identity must not kill it.
        fixify.state_path("web").write_text(
            json.dumps({"pid": os.getpid(), "identity": "someone-else"})
        )
        self.assertFalse(fixify.stop_service("web", "Web"))
        self.assertTrue(proc.identity(os.getpid()))  # still alive

    def test_port_conflict_is_refused(self) -> None:
        port = _free_port()
        server = socket.socket()
        server.bind(("127.0.0.1", port))
        server.listen()
        try:
            spec = fixify.ServiceSpec(
                "api",
                "Dummy API",
                self.tmp,
                [PY, "-c", "pass"],
                dict(os.environ),
                5,
                ("127.0.0.1", port),
            )
            with self.assertRaises(fixify.StartError) as raised:
                fixify.start_service(spec, fixify.Config({}))
            self.assertIn(f"port {port} is already in use", str(raised.exception))
            self.assertIn("Nothing was killed", str(raised.exception))
        finally:
            server.close()

    def test_missing_docker_message(self) -> None:
        original = fixify.check_docker
        fixify.check_docker = lambda: fixify.Tool(
            "Docker", False, detail="not installed", required=False
        )
        try:
            with self.assertRaises(fixify.StartError) as raised:
                fixify.start_infra(["postgres"])
            self.assertIn("Docker is needed for local postgres", str(raised.exception))
            self.assertIn("QUEUE_BACKEND=database", str(raised.exception))
        finally:
            fixify.check_docker = original


# ------------------------------------------------------------------------------------------
# Command line, in an empty repository root (no .env, no venv, no node_modules)
# ------------------------------------------------------------------------------------------


class CommandLineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="fixify-empty-root-"))

    def test_help(self) -> None:
        result = _run_launcher(["--help"], self.root)
        self.assertEqual(result.returncode, 0)
        for command in ("start", "stop", "restart", "status", "logs", "migrate", "infra", "open"):
            self.assertIn(command, result.stdout)

    def test_unknown_command(self) -> None:
        result = _run_launcher(["explode"], self.root)
        self.assertEqual(result.returncode, 2)
        self.assertIn("Unknown command", result.stdout)

    def test_no_args_non_interactive_shows_help(self) -> None:
        self.assertIn("Commands:", _run_launcher([], self.root).stdout)

    def test_start_with_missing_env_file(self) -> None:
        result = _run_launcher(["start"], self.root)
        self.assertEqual(result.returncode, 1)
        self.assertIn(".env", result.stdout)
        self.assertIn("missing", result.stdout)
        self.assertIn(".env.example", result.stdout)
        self.assertIn("Startup failed", result.stdout)
        self.assertFalse(
            (self.root / "runtime").exists() and any((self.root / "runtime").glob("*.json"))
        )

    def test_status_without_setup(self) -> None:
        result = _run_launcher(["status"], self.root)
        self.assertEqual(result.returncode, 1)
        self.assertIn("services/api/.venv missing", result.stdout)
        self.assertIn("not running", result.stdout)

    def test_stop_with_nothing_running(self) -> None:
        result = _run_launcher(["stop"], self.root)
        self.assertEqual(result.returncode, 0)
        self.assertIn("not running", result.stdout)
        self.assertIn("no containers were started by the launcher", result.stdout)

    def test_logs_without_files(self) -> None:
        result = _run_launcher(["logs", "api"], self.root)
        self.assertEqual(result.returncode, 0)
        self.assertIn("no log files yet", result.stdout)

    def test_interactive_menu(self) -> None:
        # 0 is invalid, 9 exits.
        result = _run_launcher(["menu"], self.root, stdin="0\n9\n")
        self.assertEqual(result.returncode, 0)
        self.assertIn("[1] Start Fixify", result.stdout)
        self.assertIn("[9] Exit", result.stdout)
        self.assertIn("Enter a number from 1 to 9", result.stdout)

    def test_secrets_never_printed(self) -> None:
        (self.root / ".env").write_text(
            "DATABASE_URL=postgresql+psycopg://u:sup3r-s3cret@db.invalid/x\n"
            "ANTHROPIC_API_KEY=sk-ant-very-secret\n"
        )
        result = _run_launcher(["status"], self.root)
        self.assertNotIn("sup3r-s3cret", result.stdout + result.stderr)
        self.assertNotIn("sk-ant-very-secret", result.stdout + result.stderr)
        self.assertIn("ANTHROPIC_API_KEY", result.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
