"""Fixify local development launcher.

Run through the wrappers in the repository root:

    Windows:        .\\fixify.ps1 [command]
    Linux / macOS:  ./fixify.sh [command]

Without a command an interactive menu is shown. ``--help`` lists the commands.

Standard library only, so ``status`` and ``--help`` work before the API virtual environment
exists. Everything that needs the application's own configuration (database, Redis, Alembic)
is delegated to ``probe.py`` running inside that virtual environment, so the launcher reads
settings exactly as the API and worker do.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent))
import proc  # noqa: E402

LAUNCHER_VERSION = "1.0.0"

# --------------------------------------------------------------------------------------------
# Paths (FIXIFY_ROOT overrides the repository root; used by the launcher tests)
# --------------------------------------------------------------------------------------------
ROOT = Path(os.environ.get("FIXIFY_ROOT") or Path(__file__).resolve().parents[2]).resolve()
LAUNCHER_DIR = Path(__file__).resolve().parent
API_DIR = ROOT / "services" / "api"
WEB_DIR = ROOT / "apps" / "web"
COMPOSE_FILE = ROOT / "infra" / "docker-compose.yml"
ENV_FILE = ROOT / ".env"
ENV_EXAMPLE = ROOT / ".env.example"
RUNTIME = ROOT / "runtime"
LOGS = ROOT / "logs"
APP_SERVICES = ("api", "worker", "web")
INFRA_SERVICES = ("postgres", "redis")
MIN_NODE = (20, 9)
MIN_PYTHON = (3, 12)
LOG_ROTATE_BYTES = 10 * 1024 * 1024

# --------------------------------------------------------------------------------------------
# Terminal output
# --------------------------------------------------------------------------------------------


def _enable_windows_ansi() -> bool:
    if os.name != "nt":
        return True
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)
        mode = ctypes.c_uint32()
        if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            return False
        return bool(kernel32.SetConsoleMode(handle, mode.value | 0x0004))
    except Exception:  # noqa: BLE001
        return False


def _supports_color() -> bool:
    if os.environ.get("NO_COLOR") or os.environ.get("TERM") == "dumb":
        return False
    if os.environ.get("FORCE_COLOR"):
        return True
    return sys.stdout.isatty() and _enable_windows_ansi()


def _supports_unicode() -> bool:
    encoding = (getattr(sys.stdout, "encoding", None) or "").lower().replace("-", "")
    return encoding in ("utf8", "utf8sig")


try:  # never crash on an unprintable character
    sys.stdout.reconfigure(errors="replace")  # type: ignore[attr-defined]
    sys.stderr.reconfigure(errors="replace")  # type: ignore[attr-defined]
except (AttributeError, ValueError):
    pass

COLOR = _supports_color()
UNICODE = _supports_unicode()


def _c(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m" if COLOR else text


def bold(t: str) -> str:
    return _c("1", t)


def dim(t: str) -> str:
    return _c("2", t)


def red(t: str) -> str:
    return _c("31", t)


def green(t: str) -> str:
    return _c("32", t)


def yellow(t: str) -> str:
    return _c("33", t)


def cyan(t: str) -> str:
    return _c("36", t)


SYM = {
    "ok": "✔" if UNICODE else "OK",
    "fail": "✖" if UNICODE else "XX",
    "warn": "!" if UNICODE else "!!",
    "info": "•" if UNICODE else "--",
    "skip": "○" if UNICODE else "..",
    "rule": "─" if UNICODE else "-",
}


def line(kind: str, label: str, detail: str = "") -> None:
    if sys.stdout.isatty():
        print("\r" + " " * 78 + "\r", end="")  # clear a "starting..." progress line
    painter = {"ok": green, "fail": red, "warn": yellow, "info": cyan, "skip": dim}[kind]
    mark = painter(f"[{SYM[kind]:^2}]") if UNICODE else painter(f"[{SYM[kind]}]")
    text = f"  {mark} {label:<26}"
    if detail:
        text += f" {dim(detail) if kind == 'skip' else detail}"
    print(text.rstrip(), flush=True)


def section(title: str) -> None:
    rule = SYM["rule"] * max(4, 60 - len(title))
    print(f"\n{bold(cyan(title))} {dim(rule)}", flush=True)


def note(text: str) -> None:
    print(f"      {dim(text)}", flush=True)


LOGO_UNICODE = r"""
  ███████╗██╗██╗  ██╗██╗███████╗██╗   ██╗
  ██╔════╝██║╚██╗██╔╝██║██╔════╝╚██╗ ██╔╝
  █████╗  ██║ ╚███╔╝ ██║█████╗   ╚████╔╝
  ██╔══╝  ██║ ██╔██╗ ██║██╔══╝    ╚██╔╝
  ██║     ██║██╔╝ ██╗██║██║        ██║
  ╚═╝     ╚═╝╚═╝  ╚═╝╚═╝╚═╝        ╚═╝"""

LOGO_ASCII = r"""
   _____ _      _  __
  |  ___(_)_  _(_)/ _|_   _
  | |_  | \ \/ / | |_| | | |
  |  _| | |>  <| |  _| |_| |
  |_|   |_/_/\_\_|_|  \__, |
                      |___/"""


def product_version() -> str:
    try:
        match = re.search(
            r'^version\s*=\s*"([^"]+)"', (API_DIR / "pyproject.toml").read_text(), re.M
        )
        return match.group(1) if match else "unknown"
    except OSError:
        return "unknown"


def banner() -> None:
    print(cyan(LOGO_UNICODE if UNICODE else LOGO_ASCII))
    print(f"\n      {bold('AI WEBSITE TESTING PLATFORM')}")
    print(dim(f"      Fixify v{product_version()}  {SYM['info']}  launcher v{LAUNCHER_VERSION}"))


# --------------------------------------------------------------------------------------------
# Configuration (values are read, never printed)
# --------------------------------------------------------------------------------------------


def parse_dotenv(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError:
        return values
    for raw in text.splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        key = key.strip()
        if key.startswith("export "):
            key = key[7:].strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        elif " #" in value:
            value = value.split(" #", 1)[0].rstrip()
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            values[key] = value
    return values


@dataclass
class Config:
    dotenv: dict[str, str] = field(default_factory=dict)

    def get(self, key: str, default: str = "") -> str:
        # Same precedence as the API (pydantic-settings): process environment, then .env.
        if key in os.environ:
            return os.environ[key]
        upper = {k.upper(): v for k, v in self.dotenv.items()}
        return upper.get(key.upper(), default)

    def is_set(self, key: str) -> bool:
        return bool(self.get(key).strip())

    @property
    def api_host(self) -> str:
        return self.get("API_HOST", "127.0.0.1") or "127.0.0.1"

    @property
    def api_port(self) -> int:
        return _int(self.get("API_PORT", "8000"), 8000)

    @property
    def api_connect_host(self) -> str:
        return "127.0.0.1" if self.api_host in ("0.0.0.0", "::", "") else self.api_host

    @property
    def public_app_url(self) -> str:
        return (
            self.get("PUBLIC_APP_URL", "http://localhost:3000") or "http://localhost:3000"
        ).rstrip("/")

    @property
    def web_port(self) -> int:
        if self.get("PORT"):
            return _int(self.get("PORT"), 3000)
        try:
            parts = urlsplit(self.public_app_url)
            if parts.hostname in ("localhost", "127.0.0.1") and parts.port:
                return parts.port
        except ValueError:
            pass
        return 3000

    @property
    def web_url(self) -> str:
        try:
            parts = urlsplit(self.public_app_url)
            if parts.hostname in ("localhost", "127.0.0.1") and (parts.port or 80) == self.web_port:
                return self.public_app_url
        except ValueError:
            pass
        return f"http://localhost:{self.web_port}"

    @property
    def api_url(self) -> str:
        return f"http://{self.api_connect_host}:{self.api_port}"


def _int(value: str, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def load_config() -> Config:
    return Config(parse_dotenv(ENV_FILE))


def url_host(url: str) -> str:
    try:
        return urlsplit(url).hostname or ""
    except ValueError:
        return ""


LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "0.0.0.0"}

# --------------------------------------------------------------------------------------------
# Tools
# --------------------------------------------------------------------------------------------


def venv_python() -> Path | None:
    for candidate in (
        API_DIR / ".venv" / "Scripts" / "python.exe",
        API_DIR / ".venv" / "bin" / "python",
    ):
        if candidate.exists():
            return candidate
    return None


def run(
    cmd: list[str], timeout: float = 30, cwd: Path | None = None, env: dict | None = None
) -> tuple[int, str]:
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
            env=env,
            encoding="utf-8",
            errors="replace",
            stdin=subprocess.DEVNULL,
        )
    except FileNotFoundError:
        return 127, f"{cmd[0]} not found"
    except subprocess.TimeoutExpired:
        return 124, f"{cmd[0]} timed out after {timeout:.0f} s"
    except OSError as error:
        return 126, str(error)
    return result.returncode, (result.stdout + result.stderr).strip()


def version_tuple(text: str) -> tuple[int, ...]:
    match = re.search(r"(\d+)\.(\d+)(?:\.(\d+))?", text)
    return tuple(int(g) for g in match.groups() if g is not None) if match else ()


@dataclass
class Tool:
    name: str
    ok: bool
    version: str = ""
    detail: str = ""
    required: bool = True


def check_node() -> Tool:
    node = shutil.which("node")
    if not node:
        return Tool(
            "Node.js",
            False,
            detail=f"not found (need {MIN_NODE[0]}.{MIN_NODE[1]}+): https://nodejs.org",
        )
    code, out = run([node, "--version"])
    version = out.lstrip("v")
    ok = code == 0 and version_tuple(version)[:2] >= MIN_NODE
    return Tool("Node.js", ok, version, "" if ok else f"need {MIN_NODE[0]}.{MIN_NODE[1]}+")


def check_npm() -> Tool:
    npm = shutil.which("npm")
    if not npm:
        return Tool("npm", False, detail="not found (installed with Node.js)")
    code, out = run([npm, "--version"])
    return Tool("npm", code == 0, out.splitlines()[-1] if out else "")


def check_python() -> Tool:
    python = venv_python()
    if python is None:
        return Tool(
            "Python (API venv)", False, detail="services/api/.venv missing (see README quick start)"
        )
    code, out = run([str(python), "--version"])
    version = out.replace("Python", "").strip()
    ok = code == 0 and version_tuple(version)[:2] >= MIN_PYTHON
    return Tool(
        "Python (API venv)", ok, version, "" if ok else f"need {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+"
    )


def check_docker() -> Tool:
    docker = shutil.which("docker")
    if not docker:
        return Tool("Docker", False, detail="not installed", required=False)
    code, out = run([docker, "version", "--format", "{{.Server.Version}}"], timeout=20)
    if code != 0:
        return Tool(
            "Docker",
            False,
            detail="installed, but the Docker daemon is not running",
            required=False,
        )
    return Tool("Docker", True, out.strip(), required=False)


def compose_base() -> list[str] | None:
    docker = shutil.which("docker")
    if docker and run([docker, "compose", "version", "--short"], timeout=20)[0] == 0:
        return [docker, "compose", "--env-file", str(ENV_FILE), "-f", str(COMPOSE_FILE)]
    legacy = shutil.which("docker-compose")
    if legacy and run([legacy, "version", "--short"], timeout=20)[0] == 0:
        return [legacy, "--env-file", str(ENV_FILE), "-f", str(COMPOSE_FILE)]
    return None


def check_compose() -> Tool:
    docker = shutil.which("docker")
    if docker:
        code, out = run([docker, "compose", "version", "--short"], timeout=20)
        if code == 0:
            return Tool("Docker Compose", True, out.strip(), required=False)
    legacy = shutil.which("docker-compose")
    if legacy:
        code, out = run([legacy, "version", "--short"], timeout=20)
        if code == 0:
            return Tool("Docker Compose", True, out.strip() + " (docker-compose)", required=False)
    return Tool("Docker Compose", False, detail="not available", required=False)


# --------------------------------------------------------------------------------------------
# Probes (run inside the API virtual environment)
# --------------------------------------------------------------------------------------------


def probe(name: str, timeout: float = 75) -> dict:
    python = venv_python()
    if python is None:
        return {"ok": False, "error": "API virtual environment missing (services/api/.venv)."}
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    code, out = run(
        [str(python), str(LAUNCHER_DIR / "probe.py"), name], timeout=timeout, cwd=API_DIR, env=env
    )
    for candidate in reversed(out.splitlines()):
        candidate = candidate.strip()
        if candidate.startswith("{"):
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                break
    return {
        "ok": False,
        "error": out.splitlines()[-1][:300] if out else f"probe exited with {code}",
    }


# --------------------------------------------------------------------------------------------
# Runtime state
# --------------------------------------------------------------------------------------------


def _read_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def _write_json(path: Path, data: dict) -> None:
    RUNTIME.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    tmp.replace(path)


def state_path(name: str) -> Path:
    return RUNTIME / f"{name}.json"


@dataclass
class ServiceState:
    name: str
    running: bool
    pid: int | None = None
    child_pid: int | None = None
    started_at: str = ""
    stale_cleared: bool = False


def service_state(name: str, clean_stale: bool = True) -> ServiceState:
    """Validated state of a launcher-managed service. Clears stale state files."""
    data = _read_json(state_path(name))
    if not data:
        return ServiceState(name, False)
    supervisor_alive = proc.is_ours(data.get("pid"), data.get("identity"))
    child = _read_json(RUNTIME / f"{name}.child.json") or {}
    child_alive = proc.is_ours(child.get("pid"), child.get("identity"))
    if supervisor_alive or child_alive:
        return ServiceState(
            name,
            True,
            data.get("pid") if supervisor_alive else None,
            child.get("pid") if child_alive else None,
            data.get("started_at", ""),
        )
    if clean_stale:
        for suffix in (".json", ".child.json", ".stop"):
            (RUNTIME / f"{name}{suffix}").unlink(missing_ok=True)
    return ServiceState(name, False, stale_cleared=True)


def uptime(started_at: str) -> str:
    try:
        seconds = int((datetime.now(UTC) - datetime.fromisoformat(started_at)).total_seconds())
    except ValueError:
        return ""
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m {seconds % 60}s"
    return f"{seconds // 3600}h {seconds % 3600 // 60}m"


# --------------------------------------------------------------------------------------------
# Health checks
# --------------------------------------------------------------------------------------------


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):  # noqa: ANN002, ANN003
        return None


def http_status(url: str, timeout: float = 5) -> int | None:
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(
            urllib.request.Request(url, headers={"User-Agent": "fixify-launcher"}), timeout=timeout
        ) as r:
            return r.status
    except urllib.error.HTTPError as error:
        return error.code
    except (urllib.error.URLError, OSError, ValueError):
        return None


def port_in_use(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.75):
            return True
    except OSError:
        return False


def port_owner(port: int) -> str:
    """Best-effort, read-only description of the process listening on a port (for messages)."""
    pid = None
    if os.name == "nt":
        code, out = run(["netstat", "-ano", "-p", "TCP"], timeout=15)
        code6, out6 = run(["netstat", "-ano", "-p", "TCPv6"], timeout=15)
        rows = [r.split() for r in (out + "\n" + out6).splitlines()]
        rows = [
            c
            for c in rows
            if len(c) >= 5 and c[0] == "TCP" and c[1].rsplit(":", 1)[-1] == str(port)
        ]
        # Listener rows first (foreign address *:0; the state label is not always LISTENING),
        # then any server-side connection on that local port.
        rows.sort(key=lambda c: 0 if c[2].endswith(":0") else 1)
        for cols in rows:
            if _int(cols[-1], 0) > 0:
                pid = _int(cols[-1], 0)
                break
    elif shutil.which("lsof"):
        code, out = run(["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-t"], timeout=15)
        pid = _int(out.split()[0], 0) if code == 0 and out.split() else None
    if not pid:
        return ""
    what = proc.describe(pid)
    return f"PID {pid}" + (f" ({what[:140]})" if what else "")


def api_ready(config: Config) -> tuple[bool, str]:
    status = http_status(f"{config.api_url}/api/v1/health/ready")
    if status == 200:
        return True, "ready (database and queue reachable)"
    if status is None:
        return False, "not responding"
    return False, f"/health/ready returned HTTP {status}"


def web_ready(config: Config) -> tuple[bool, str]:
    status = http_status(f"http://127.0.0.1:{config.web_port}/", timeout=30)
    if status is None:
        return False, "not responding"
    if status < 500:
        return True, f"HTTP {status}"
    return False, f"HTTP {status}"


WORKER_MARKERS = ("Worker started", "Job worker started", "Scheduler started")


def _log_since(path: Path, offset: int) -> str:
    try:
        with path.open("rb") as handle:
            handle.seek(offset)
            return handle.read().decode("utf-8", errors="replace")
    except OSError:
        return ""


def worker_ready(text: str) -> tuple[bool | None, str]:
    """True = all loops started, False = an error was logged, None = still starting."""
    for raw in text.splitlines():
        if '"level": "ERROR"' in raw or '"level": "CRITICAL"' in raw:
            try:
                message = json.loads(raw).get("message", raw)
            except json.JSONDecodeError:
                message = raw
            return False, f"logged an error: {message[:160]}"
        if raw.startswith("Traceback"):
            return False, "crashed (traceback in log)"
    missing = [m for m in WORKER_MARKERS if m not in text]
    if not missing:
        return True, "scan worker, job worker and scheduler started"
    return None, f"waiting for: {', '.join(missing)}"


# --------------------------------------------------------------------------------------------
# Services
# --------------------------------------------------------------------------------------------


@dataclass
class ServiceSpec:
    name: str
    title: str
    cwd: Path
    command: list[str]
    env: dict[str, str]
    timeout: float
    port: tuple[str, int] | None = None


def web_command() -> list[str]:
    """Derived from apps/web/package.json ``scripts.dev``."""
    try:
        dev = json.loads((WEB_DIR / "package.json").read_text())["scripts"]["dev"]
    except (OSError, KeyError, json.JSONDecodeError):
        dev = ""
    next_bin = WEB_DIR / "node_modules" / "next" / "dist" / "bin" / "next"
    node = shutil.which("node")
    parts = dev.split()
    # Run "next ..." with node directly: no npm / cmd.exe wrapper between the supervisor and
    # Next.js, so the shutdown signal reaches the server itself.
    if parts[:1] == ["next"] and next_bin.exists() and node:
        return [node, str(next_bin), *parts[1:]]
    npm = shutil.which("npm") or "npm"
    return [npm, "run", "dev"]


def web_env_defines(key: str) -> bool:
    for name in (".env.local", ".env.development.local", ".env.development", ".env"):
        if key in parse_dotenv(WEB_DIR / name):
            return True
    return key in os.environ


def build_specs(config: Config) -> dict[str, ServiceSpec]:
    python = str(venv_python() or "python")
    base = dict(os.environ, PYTHONUNBUFFERED="1", PYTHONIOENCODING="utf-8")
    api_env = dict(base, API_HOST=config.api_host, API_PORT=str(config.api_port))
    web_env = dict(os.environ, PORT=str(config.web_port), NODE_ENV="development", FORCE_COLOR="0")
    if not web_env_defines("API_INTERNAL_URL"):
        web_env["API_INTERNAL_URL"] = config.api_url
    return {
        "api": ServiceSpec(
            "api",
            "API (FastAPI)",
            API_DIR,
            [python, "-m", "app.serve"],
            api_env,
            60,
            (config.api_connect_host, config.api_port),
        ),
        "worker": ServiceSpec("worker", "Worker", API_DIR, [python, "-m", "app.worker"], base, 45),
        "web": ServiceSpec(
            "web",
            "Web (Next.js)",
            WEB_DIR,
            web_command(),
            web_env,
            180,
            ("127.0.0.1", config.web_port),
        ),
    }


def _rotate(log: Path) -> None:
    try:
        if log.exists() and log.stat().st_size > LOG_ROTATE_BYTES:
            log.replace(log.with_suffix(".log.1"))
    except OSError:
        pass


def _tail(path: Path, lines: int) -> list[str]:
    try:
        with path.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - 256 * 1024))
            return handle.read().decode("utf-8", errors="replace").splitlines()[-lines:]
    except OSError:
        return []


_ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]|\x1b\][^\x07]*\x07")


def strip_ansi(text: str) -> str:
    return _ANSI.sub("", text)


class StartError(RuntimeError):
    pass


def start_service(spec: ServiceSpec, config: Config) -> bool:
    """Start one service and wait for its health check. Returns True if this call started it."""
    state = service_state(spec.name)
    if state.stale_cleared:
        line("info", spec.title, "stale state file from an earlier run cleared")
    if state.running:
        ok, detail = check_service_health(spec.name, config)
        if ok:
            line(
                "ok", spec.title, f"already running (PID {state.pid or state.child_pid}), {detail}"
            )
            return False
        raise StartError(
            f"{spec.title} is already running (PID {state.pid}) but unhealthy: {detail}. "
            f"Run 'fixify restart' or check 'fixify logs {spec.name}'."
        )
    if spec.port and port_in_use(*spec.port):
        owner = port_owner(spec.port[1])
        raise StartError(
            f"{spec.title}: port {spec.port[1]} is already in use by a process the launcher "
            f"did not start{': ' + owner if owner else ''}.\n      If that is a manually "
            f"started Fixify service, stop it (Ctrl+C in its terminal) and run start "
            f"again. Nothing was killed."
        )

    LOGS.mkdir(parents=True, exist_ok=True)
    RUNTIME.mkdir(parents=True, exist_ok=True)
    log = LOGS / f"{spec.name}.log"
    _rotate(log)
    offset = log.stat().st_size if log.exists() else 0
    command = [
        str(Path(sys.executable)),
        str(LAUNCHER_DIR / "supervise.py"),
        "--name",
        spec.name,
        "--cwd",
        str(spec.cwd),
        "--log",
        str(log),
        "--runtime",
        str(RUNTIME),
        "--",
        *spec.command,
    ]
    supervisor = subprocess.Popen(
        command,
        cwd=str(ROOT),
        env=spec.env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        **proc.popen_flags(new_console=True),
    )
    _write_json(
        state_path(spec.name),
        {
            "name": spec.name,
            "pid": supervisor.pid,
            "identity": proc.identity(supervisor.pid),
            "started_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "command": spec.command[:3],
            "log": str(log),
        },
    )

    deadline = time.monotonic() + spec.timeout
    detail = "starting"
    if sys.stdout.isatty():
        print(
            f"  {dim(SYM['info'])} {spec.title:<26} {dim('starting…' if UNICODE else 'starting')}",
            end="\r",
            flush=True,
        )
    while time.monotonic() < deadline:
        if supervisor.poll() is not None:
            tail = "\n".join(
                f"      {dim(strip_ansi(t))}" for t in _tail(log, 12) if strip_ansi(t).strip()
            )
            raise StartError(
                f"{spec.title} exited during startup (exit code {supervisor.returncode}). "
                f"Last log lines ({log}):\n{tail}"
            )
        if spec.name == "worker":
            ready, detail = worker_ready(_log_since(log, offset))
            if ready is False:
                raise StartError(f"Worker {detail}. See {log}.")
            if ready:
                # No health endpoint: confirm it stays up and quiet for a short window.
                settle = time.monotonic() + 3
                while time.monotonic() < settle and supervisor.poll() is None:
                    time.sleep(0.25)
                again, detail2 = worker_ready(_log_since(log, offset))
                if supervisor.poll() is None and again:
                    line("ok", spec.title, f"running (PID {supervisor.pid}), {detail}")
                    return True
                raise StartError(f"Worker stopped right after starting: {detail2}. See {log}.")
        else:
            ok, detail = check_service_health(spec.name, config)
            if ok:
                line("ok", spec.title, f"running (PID {supervisor.pid}), {detail}")
                return True
        time.sleep(0.5)
    raise StartError(
        f"{spec.title} did not become healthy within {spec.timeout:.0f} s ({detail}). Log: {log}"
    )


def check_service_health(name: str, config: Config) -> tuple[bool, str]:
    if name == "api":
        return api_ready(config)
    if name == "web":
        return web_ready(config)
    log = LOGS / "worker.log"
    tail = "\n".join(_tail(log, 400))
    marker = "===== fixify launcher: starting worker"
    recent = tail[tail.rfind(marker) :] if marker in tail else tail
    ready, detail = worker_ready(recent)
    if ready is False:
        return True, f"process running; last start {detail}"
    return True, "process running (the worker has no health endpoint)"


def stop_service(name: str, title: str, grace: float = 25) -> bool:
    """Stop a launcher-managed service. Never touches processes the launcher did not start."""
    state = service_state(name)
    if not state.running:
        line(
            "skip",
            title,
            "not running" + (" (had already exited; state cleared)" if state.stale_cleared else ""),
        )
        return False
    data = _read_json(state_path(name)) or {}
    child = _read_json(RUNTIME / f"{name}.child.json") or {}
    (RUNTIME / f"{name}.stop").write_text("stop")
    deadline = time.monotonic() + grace
    while time.monotonic() < deadline:
        if not proc.is_ours(data.get("pid"), data.get("identity")) and not proc.is_ours(
            child.get("pid"), child.get("identity")
        ):
            break
        time.sleep(0.3)
    forced = False
    for record in (child, data):  # last resort, only for processes verified as ours
        if proc.is_ours(record.get("pid"), record.get("identity")):
            proc.kill_tree(record["pid"])
            forced = True
    for suffix in (".json", ".child.json", ".stop"):
        (RUNTIME / f"{name}{suffix}").unlink(missing_ok=True)
    line("ok", title, "stopped" + (" (forced after grace period)" if forced else ""))
    return True


# --------------------------------------------------------------------------------------------
# Infrastructure (Docker Compose)
# --------------------------------------------------------------------------------------------


def container_state(base: list[str], service: str) -> tuple[str, str]:
    code, out = run(base + ["ps", "-a", "-q", service], timeout=30)
    container = out.strip().splitlines()[-1] if code == 0 and out.strip() else ""
    if not container:
        return "absent", ""
    code, out = run(
        [
            "docker",
            "inspect",
            "-f",
            "{{.State.Status}}|{{if .State.Health}}{{.State.Health.Status}}{{end}}",
            container,
        ]
    )
    if code != 0:
        return "unknown", ""
    status, _, health = out.strip().partition("|")
    return status, health


def infra_needs(settings: dict) -> dict[str, bool]:
    """Which Compose services this configuration needs: a local URL on the published port."""
    db = settings.get("database", {})
    redis = settings.get("redis", {})
    return {
        "postgres": bool(db.get("local"))
        and db.get("scheme") == "postgresql"
        and db.get("port") in (None, 5432),
        "redis": bool(settings.get("redis_needed"))
        and bool(redis.get("local"))
        and redis.get("port") in (None, 6379),
    }


def wait_healthy(base: list[str], services: list[str], timeout: float = 90) -> None:
    deadline = time.monotonic() + timeout
    pending = list(services)
    while pending and time.monotonic() < deadline:
        for service in list(pending):
            status, health = container_state(base, service)
            if status == "running" and health in ("healthy", ""):
                line("ok", f"{service} container", f"running, {health or 'no health check'}")
                pending.remove(service)
            elif status in ("exited", "dead"):
                raise StartError(f"{service} container {status}. See: fixify logs {service}")
        if pending:
            time.sleep(1)
    if pending:
        raise StartError(
            f"Timed out waiting for {', '.join(pending)} to become healthy "
            f"(fixify logs {pending[0]})."
        )


def start_infra(services: list[str]) -> list[str]:
    """docker compose up -d for the given services. Returns the ones this call started."""
    if not COMPOSE_FILE.exists():
        raise StartError(f"{COMPOSE_FILE.relative_to(ROOT)} not found.")
    docker = check_docker()
    if not docker.ok:
        raise StartError(
            f"Docker is needed for local {' and '.join(services)}, but {docker.detail}.\n"
            "      Start Docker Desktop (or the docker service), or point DATABASE_URL / "
            "REDIS_URL in .env at\n      servers that are already running (for no Redis: "
            "QUEUE_BACKEND=database, REDIS_REQUIRED=false)."
        )
    base = compose_base()
    if base is None:
        raise StartError("Docker Compose is not available (docker compose / docker-compose).")
    already = [s for s in services if container_state(base, s)[0] == "running"]
    published = {"postgres": 5432, "redis": 6379}  # from infra/docker-compose.yml
    for service in services:
        port = published[service]
        if service not in already and port_in_use("127.0.0.1", port):
            owner = f" ({port_owner(port)})" if port_owner(port) else ""
            setting = "DATABASE_URL" if service == "postgres" else "REDIS_URL"
            raise StartError(
                f"Cannot start the {service} container: port {port} is already used by "
                f"another process{owner}.\n      If that is a native {service} server, point "
                f"{setting} in .env at it instead of using Docker, or stop it. "
                f"Nothing was started or killed."
            )
    # Streamed, not captured: the first run pulls images, which can take minutes.
    print(f"  {dim('$ docker compose up -d ' + ' '.join(services))}", flush=True)
    try:
        code = subprocess.call(
            base + ["up", "-d", *services], stdin=subprocess.DEVNULL, timeout=900
        )
    except subprocess.TimeoutExpired:
        raise StartError("docker compose up did not finish within 15 minutes.") from None
    if code != 0:
        raise StartError(f"docker compose up failed (exit code {code}); see the output above.")
    wait_healthy(base, services)
    started = [s for s in services if s not in already]
    if started:
        record = _read_json(RUNTIME / "infra.json") or {"started": []}
        record["started"] = sorted(set(record.get("started", [])) | set(started))
        _write_json(RUNTIME / "infra.json", record)
    return started


def stop_infra() -> None:
    record = _read_json(RUNTIME / "infra.json") or {}
    services = [s for s in record.get("started", []) if s in INFRA_SERVICES]
    if not services:
        line("skip", "Infrastructure", "no containers were started by the launcher")
        return
    base = compose_base()
    if base is None:
        line("warn", "Infrastructure", f"Docker unavailable; could not stop {', '.join(services)}")
        return
    # "stop", never "down -v": containers and volumes (database data) are kept.
    code, out = run(base + ["stop", *services], timeout=120)
    if code == 0:
        for service in services:
            line("ok", f"{service} container", "stopped (data volume kept)")
        (RUNTIME / "infra.json").unlink(missing_ok=True)
    else:
        line("fail", "Infrastructure", out[-300:])


# --------------------------------------------------------------------------------------------
# Environment validation
# --------------------------------------------------------------------------------------------


def check_env_files() -> bool:
    ok = True
    if ENV_FILE.exists():
        line("ok", ".env", "found (values are never displayed)")
    else:
        ok = False
        line("fail", ".env", "missing")
        hint = "Copy-Item .env.example .env" if os.name == "nt" else "cp .env.example .env"
        note(f"Create it from the template, then edit DATABASE_URL:  {hint}")
    if venv_python():
        line("ok", "API virtual environment", "services/api/.venv")
    else:
        ok = False
        line("fail", "API virtual environment", "services/api/.venv missing")
        note('cd services/api; python -m venv .venv; then install with: pip install -e ".[dev]"')
    if (WEB_DIR / "node_modules").exists():
        line("ok", "Web dependencies", "apps/web/node_modules")
    else:
        ok = False
        line("fail", "Web dependencies", "apps/web/node_modules missing")
        note("cd apps/web; npm install")
    return ok


def report_env_vars(config: Config, settings: dict | None) -> bool:
    """Show which settings are configured. Returns False if a required one is missing."""
    ok = True
    prod = (settings or {}).get("is_production", config.get("APP_ENV") == "production")

    def show(key: str, required: bool, effect: str = "", unused: bool = False) -> None:
        nonlocal ok
        if config.is_set(key):
            line("ok", key, "configured" + (" (not used by this configuration)" if unused else ""))
        elif required:
            ok = False
            line("fail", key, "not set (required)")
        else:
            line("skip", key, f"not set (optional{': ' + effect if effect else ''})")

    show("DATABASE_URL", True)
    if settings and settings.get("database_is_default"):
        line("warn", "DATABASE_URL", "is the .env.example placeholder (local Docker PostgreSQL)")
    redis_needed = (settings or {}).get(
        "redis_needed", config.get("QUEUE_BACKEND", "redis") == "redis"
    )
    if redis_needed:
        show("REDIS_URL", True)
    else:
        show("REDIS_URL", False, "Redis not used by this configuration", unused=True)
    show("SECRET_KEY", bool(prod), "a random key is generated per process in development")
    show("ANTHROPIC_API_KEY", False, "AI analysis and fixes disabled")
    show("GITHUB_CLIENT_ID", False, "GitHub connection disabled")
    show("GITHUB_CLIENT_SECRET", False, "GitHub connection disabled")
    show("TOKEN_ENCRYPTION_KEY", False, "needed with GitHub")
    if config.get("EMAIL_BACKEND", "console") == "smtp":
        show("SMTP_HOST", True)
    return ok


# --------------------------------------------------------------------------------------------
# Commands
# --------------------------------------------------------------------------------------------


def _interactive() -> bool:
    return sys.stdin.isatty() and not os.environ.get("FIXIFY_NONINTERACTIVE")


def confirm(question: str, default: bool = False) -> bool:
    if not _interactive():
        return False
    suffix = " [Y/n] " if default else " [y/N] "
    try:
        answer = input(f"  {yellow('?')} {question}{suffix}").strip().lower()
    except EOFError:
        return default
    return default if not answer else answer in ("y", "yes")


def prepare_backend(config: Config, migrate: str = "ask") -> dict:
    """Validate config, start needed infrastructure, check DB/Redis and migrations."""
    section("Environment")
    if not check_env_files():
        raise StartError("Fix the items above, then run 'fixify start' again.")
    settings = probe("settings")
    if not settings.get("ok"):
        for detail in settings.get("details", []):
            note(detail)
        raise StartError(f"Configuration could not be loaded: {settings.get('error')}")
    if not report_env_vars(config, settings):
        raise StartError("A required setting is missing in .env (see above).")

    section("Tools")
    tools = [check_node(), check_npm(), check_python()]
    for tool in tools:
        line("ok" if tool.ok else "fail", tool.name, tool.version or tool.detail)
    if not all(t.ok for t in tools):
        raise StartError("A required tool is missing or too old (see above).")

    section("Infrastructure")
    needs = infra_needs(settings)

    def where(info: dict) -> str:
        return f"{info.get('host') or info.get('scheme')}" + (
            f":{info['port']}" if info.get("port") else ""
        )

    if not needs["postgres"]:
        line(
            "skip",
            "PostgreSQL container",
            f"not needed: DATABASE_URL points at {where(settings['database'])}",
        )
    if not needs["redis"]:
        why = (
            "Redis not used (QUEUE_BACKEND=database)"
            if not settings.get("redis_needed")
            else f"REDIS_URL points at {where(settings['redis'])}"
        )
        line("skip", "Redis container", f"not needed: {why}")
    wanted = []
    for service, probe_name in (("postgres", "db"), ("redis", "redis")):
        if needs[service]:
            if probe(probe_name).get("ok"):
                line("ok", f"{service}", "already reachable on localhost; Docker not needed")
            else:
                wanted.append(service)
    if wanted:
        start_infra(wanted)

    section("Connectivity")
    db = probe("db")
    if not db.get("ok"):
        raise StartError(f"PostgreSQL at {db.get('host')} is unreachable: {db.get('error')}")
    line("ok", "PostgreSQL", f"{db.get('host')} ({db.get('version')})")
    redis = probe("redis")
    if redis.get("skipped"):
        line("skip", "Redis", "not required by this configuration")
    elif not redis.get("ok"):
        raise StartError(f"Redis at {redis.get('host')} is unreachable: {redis.get('error')}")
    else:
        line("ok", "Redis", f"{redis.get('host')} (Redis {redis.get('version')})")

    section("Database migrations")
    migrations = probe("migrations")
    if not migrations.get("ok"):
        raise StartError(f"Could not read the migration state: {migrations.get('error')}")
    pending = migrations.get("pending", [])
    current = ", ".join(migrations.get("current") or ["none (empty database)"])
    if not pending:
        line("ok", "Schema", f"up to date at {current}")
    else:
        line("warn", "Schema", f"{len(pending)} pending migration(s): {', '.join(pending)}")
        auto = migrate == "yes" or config.get("FIXIFY_AUTO_MIGRATE").lower() in ("1", "true", "yes")
        if auto or (
            migrate == "ask"
            and confirm("Apply them now (alembic upgrade head, no data is deleted)?")
        ):
            if run_alembic_upgrade() != 0:
                raise StartError("Migration failed; services were not started.")
        else:
            raise StartError(
                "The database schema is behind the code. Run 'fixify migrate' "
                "(or 'fixify start --migrate'), then start again."
            )
    return settings


def cmd_start(args: list[str]) -> int:
    config = load_config()
    migrate = "yes" if "--migrate" in args else "ask"
    banner()
    started: list[str] = []
    specs = build_specs(config)
    try:
        prepare_backend(config, migrate)
        section("Services")
        for name in APP_SERVICES:
            if start_service(specs[name], config):
                started.append(name)
    except StartError as error:
        print()
        line("fail", "Startup failed", "")
        print(f"      {red(str(error))}")
        rollback(started, specs)
        return 1
    except KeyboardInterrupt:
        print()
        line("warn", "Interrupted", "Ctrl+C: stopping what this run started")
        rollback(started, specs)
        return 130
    summary(config)
    return 0


def rollback(started: list[str], specs: dict[str, ServiceSpec]) -> None:
    """Stop the services this run started, so no half-started application is left behind."""
    # Includes a service that was launched but never became healthy (it has a state file
    # written during this run, but is not in ``started``). Services that were already running
    # before this run are left alone.
    candidates = [n for n in APP_SERVICES if n in started or _started_this_run(n)]
    if not candidates:
        return
    print(f"      {dim('Stopping services started by this run:')}")
    for name in reversed(candidates):
        stop_service(name, specs[name].title)


_RUN_STARTED = datetime.now(UTC)


def _started_this_run(name: str) -> bool:
    data = _read_json(state_path(name)) or {}
    try:
        return datetime.fromisoformat(data.get("started_at", "")) >= _RUN_STARTED.replace(
            microsecond=0
        )
    except ValueError:
        return False


def summary(config: Config) -> None:
    section("Fixify is running")
    print(f"  {bold('Web app')}   {cyan(config.web_url)}")
    print(f"  {bold('API')}       {cyan(config.api_url)}   {dim('(health: /api/v1/health/ready)')}")
    print(f"  {bold('Logs')}      {dim(str(LOGS))}")
    print(f"\n  {dim('Services run in the background. Stop them with:')} fixify stop")


def cmd_infra(args: list[str]) -> int:
    banner()
    section("Infrastructure")
    try:
        if "--all" in args:
            services = list(INFRA_SERVICES)
        else:
            settings = probe("settings")
            if not settings.get("ok"):
                raise StartError(f"Configuration could not be loaded: {settings.get('error')}")
            needs = infra_needs(settings)
            services = [s for s in INFRA_SERVICES if needs[s]]
            if not services:
                line("skip", "PostgreSQL", f"external: {settings['database']['host']}")
                line(
                    "skip",
                    "Redis",
                    "not used"
                    if not settings.get("redis_needed")
                    else f"external: {settings['redis']['host']}",
                )
                note(
                    "This .env needs no local containers. To start local PostgreSQL and Redis "
                    "anyway: fixify infra --all"
                )
                return 0
        start_infra(services)
    except StartError as error:
        line("fail", "Infrastructure", "")
        print(f"      {red(str(error))}")
        return 1
    return 0


def cmd_stop(args: list[str]) -> int:
    config = load_config()
    specs = build_specs(config)
    section("Stopping Fixify")
    for name in reversed(APP_SERVICES):
        stop_service(name, specs[name].title)
    if "--keep-infra" in args:
        line("skip", "Infrastructure", "kept running (--keep-infra)")
    else:
        stop_infra()
    return 0


def cmd_restart(args: list[str]) -> int:
    config = load_config()
    specs = build_specs(config)
    section("Restarting application services")
    for name in reversed(APP_SERVICES):
        stop_service(name, specs[name].title)
    note("Infrastructure containers are left as they are.")
    return cmd_start(args)


def cmd_status(args: list[str]) -> int:  # noqa: ARG001
    config = load_config()
    banner()
    section("Tools")
    tools = [check_python(), check_node(), check_npm(), check_docker(), check_compose()]
    for tool in tools:
        kind = "ok" if tool.ok else ("fail" if tool.required else "warn")
        label = tool.name + ("" if tool.required else " (optional)")
        line(kind, label, tool.version or tool.detail)

    section("Configuration")
    files_ok = check_env_files()
    settings = (
        probe("settings") if venv_python() else {"ok": False, "error": "no virtual environment"}
    )
    if settings.get("ok"):
        report_env_vars(config, settings)
        line("info", "APP_ENV", settings.get("app_env", ""))
        line("info", "Queue backend", settings.get("queue_backend", ""))
    elif ENV_FILE.exists():
        report_env_vars(config, None)
        line("fail", "Settings", f"could not be loaded: {settings.get('error', '')}")
        for detail in settings.get("details", []):
            note(detail)

    section("Infrastructure")
    healthy = True
    if settings.get("ok"):
        needs = infra_needs(settings)
        db = probe("db")
        healthy &= bool(db.get("ok"))
        line(
            "ok" if db.get("ok") else "fail",
            "PostgreSQL",
            f"{db.get('host')} "
            + (f"({db.get('version')})" if db.get("ok") else f"- {db.get('error')}"),
        )
        redis = probe("redis")
        if redis.get("skipped"):
            line("skip", "Redis", "not required by this configuration")
        else:
            healthy &= bool(redis.get("ok"))
            line(
                "ok" if redis.get("ok") else "fail",
                "Redis",
                f"{redis.get('host')} "
                + (
                    f"(Redis {redis.get('version')})"
                    if redis.get("ok")
                    else f"- {redis.get('error')}"
                ),
            )
        base = compose_base() if any(needs.values()) and check_docker().ok else None
        for service in INFRA_SERVICES:
            if needs[service] and base:
                status, health = container_state(base, service)
                line(
                    "ok" if status == "running" else "warn",
                    f"{service} container",
                    f"{status}{', ' + health if health else ''}",
                )
        if db.get("ok"):
            migrations = probe("migrations")
            if migrations.get("ok"):
                pending = migrations.get("pending", [])
                line(
                    "ok" if not pending else "warn",
                    "Migrations",
                    "up to date"
                    if not pending
                    else f"{len(pending)} pending: {', '.join(pending)}",
                )
    else:
        line("skip", "PostgreSQL / Redis", "configuration not loaded")
        healthy = False

    section("Services")
    specs = build_specs(config)
    for name in APP_SERVICES:
        state = service_state(name)
        if state.running:
            ok, detail = check_service_health(name, config)
            healthy &= ok
            line(
                "ok" if ok else "fail",
                specs[name].title,
                f"PID {state.pid or state.child_pid}, up {uptime(state.started_at)}, {detail}",
            )
        else:
            healthy = False
            busy = specs[name].port and port_in_use(*specs[name].port)
            line(
                "warn" if busy else "skip",
                specs[name].title,
                "not running"
                + (f" (port {specs[name].port[1]} is used by another process)" if busy else ""),
            )
    print(f"\n  {bold('Web app')} {config.web_url}   {bold('API')} {config.api_url}")
    return 0 if healthy and files_ok else 1


def _follow(paths: dict[str, Path], lines: int, follow: bool) -> None:
    prefix = len(paths) > 1
    offsets = {}
    for name, path in paths.items():
        for text in _tail(path, lines):
            print(f"{cyan(name.ljust(6)) + ' | ' if prefix else ''}{text}")
        offsets[name] = path.stat().st_size if path.exists() else 0
    if not follow:
        return
    print(dim("-- following; press Ctrl+C to stop (services keep running) --"), flush=True)
    try:
        while True:
            for name, path in paths.items():
                size = path.stat().st_size if path.exists() else 0
                if size < offsets[name]:
                    offsets[name] = 0  # rotated or truncated
                if size > offsets[name]:
                    chunk = _log_since(path, offsets[name])
                    offsets[name] = size
                    for text in chunk.splitlines():
                        print(f"{cyan(name.ljust(6)) + ' | ' if prefix else ''}{text}", flush=True)
            time.sleep(0.5)
    except KeyboardInterrupt:
        print()


def cmd_logs(args: list[str]) -> int:
    follow = "-f" in args or "--follow" in args
    lines = 100
    if "-n" in args:
        index = args.index("-n")
        lines = _int(args[index + 1] if index + 1 < len(args) else "", 100)
    names = [a for a in args if not a.startswith("-") and not a.isdigit()]
    target = names[0] if names else None
    if target is None:
        if not _interactive():
            target = "all"
        else:
            section("View logs")
            options = ["web", "api", "worker", "postgres", "redis", "all"]
            labels = [
                "Frontend (Next.js)",
                "API (FastAPI)",
                "Worker",
                "PostgreSQL (Docker)",
                "Redis (Docker)",
                "All application logs",
            ]
            for number, label in enumerate(labels, 1):
                print(f"  [{number}] {label}")
            print("  [0] Back")
            choice = _read_choice("Select a log")
            if choice is None or choice == "0" or not choice.isdigit() or not 1 <= int(choice) <= 6:
                return 0
            target = options[int(choice) - 1]
            follow = confirm("Follow new output?", default=True)
    aliases = {"frontend": "web", "backend": "api", "db": "postgres", "database": "postgres"}
    target = aliases.get(target, target)
    if target in INFRA_SERVICES:
        base = compose_base() if check_docker().ok else None
        if base is None:
            line(
                "fail",
                f"{target} logs",
                "Docker is not available (the container is not running here)",
            )
            return 1
        command = base + ["logs", "--tail", str(lines), *(["-f"] if follow else []), target]
        try:
            return subprocess.call(command)
        except KeyboardInterrupt:
            return 0
    if target == "all":
        paths = {n: LOGS / f"{n}.log" for n in APP_SERVICES}
    elif target in APP_SERVICES:
        paths = {target: LOGS / f"{target}.log"}
    else:
        print(red(f"Unknown log '{target}'. Choose: web, api, worker, postgres, redis, all."))
        return 2
    existing = {n: p for n, p in paths.items() if p.exists()}
    if not existing:
        line("skip", "Logs", f"no log files yet in {LOGS} (start Fixify first)")
        return 0
    _follow(existing if not follow else paths, lines, follow)
    return 0


def run_alembic_upgrade() -> int:
    python = venv_python()
    if python is None:
        line("fail", "Migrations", "API virtual environment missing")
        return 1
    print(f"  {dim('$ alembic upgrade head')}", flush=True)
    code = subprocess.call(
        [str(python), "-m", "alembic", "upgrade", "head"],
        cwd=API_DIR,
        env=dict(os.environ, PYTHONIOENCODING="utf-8"),
    )
    if code != 0:
        line("fail", "Migrations", f"alembic exited with code {code}; the database was not reset")
        return code
    after = probe("migrations")
    if after.get("ok") and not after.get("pending"):
        line("ok", "Migrations", f"applied; schema at {', '.join(after.get('current', []))}")
        return 0
    line("fail", "Migrations", "alembic finished but revisions are still pending")
    return 1


def cmd_migrate(args: list[str]) -> int:
    section("Database migrations")
    if not venv_python():
        line("fail", "API virtual environment", "services/api/.venv missing")
        return 1
    db = probe("db")
    if not db.get("ok"):
        line("fail", "Database", f"{db.get('host')} unreachable: {db.get('error')}")
        note("Nothing was changed. Start the database first (fixify infra) and retry.")
        return 1
    line("ok", "Database", f"{db.get('host')} ({db.get('version')})")
    state = probe("migrations")
    if not state.get("ok"):
        line("fail", "Migration state", state.get("error", ""))
        return 1
    current = ", ".join(state.get("current") or ["none (empty database)"])
    line("info", "Current revision", current)
    line("info", "Target (head)", ", ".join(state.get("heads", [])))
    pending = state.get("pending", [])
    if not pending:
        line("ok", "Schema", "already up to date; nothing to do")
        return 0
    line("warn", "Pending", ", ".join(pending))
    note("Action: alembic upgrade head (forward only; nothing is dropped or reset).")
    if "--yes" not in args and "-y" not in args and _interactive():
        if not confirm("Apply these migrations?"):
            line("skip", "Migrations", "cancelled; nothing was changed")
            return 1
    return run_alembic_upgrade()


def cmd_open(args: list[str]) -> int:  # noqa: ARG001
    config = load_config()
    ok, detail = web_ready(config)
    if not ok:
        line("fail", "Web app", f"{config.web_url} is {detail}. Start Fixify first: fixify start")
        return 1
    line("ok", "Opening", config.web_url)
    webbrowser.open(config.web_url)
    return 0


HELP = """
Usage:  {cmd} [command] [options]

Commands:
  start [--migrate]     Validate config, start needed infrastructure, check the database and
                        migrations, then start the API, worker and web app (with health checks).
                        --migrate applies pending migrations without asking.
  infra [--all]         Start only the local PostgreSQL / Redis containers this .env needs
                        (--all: both, regardless of .env).
  stop [--keep-infra]   Stop the web app, worker and API, then the containers the launcher
                        started. Data volumes are always kept.
  restart [--migrate]   Stop and start the application services (containers are not recreated).
  status                Tools, configuration, database, Redis, migrations and services.
  logs [name] [-f] [-n N]
                        name: web | api | worker | postgres | redis | all (default: all)
  migrate [--yes]       Show pending Alembic migrations and apply them (upgrade only).
  open                  Open the web app in your browser.
  menu                  Interactive menu (also shown when no command is given).
  help, --help          This help.

Files:  logs/<service>.log   runtime/ (launcher state; both git-ignored)
"""


def cmd_help(args: list[str]) -> int:  # noqa: ARG001
    wrapper = ".\\fixify.ps1" if os.environ.get("FIXIFY_WRAPPER") == "ps1" else "./fixify.sh"
    print(HELP.format(cmd=wrapper))
    return 0


def _read_choice(prompt: str) -> str | None:
    try:
        return input(f"\n  {bold(prompt)}: ").strip()
    except EOFError:
        return None


MENU: list[tuple[str, Callable[[list[str]], int] | None]] = [
    ("Start Fixify", cmd_start),
    ("Start Infrastructure", cmd_infra),
    ("Stop Fixify", cmd_stop),
    ("Restart Fixify", cmd_restart),
    ("View Logs", cmd_logs),
    ("Run Database Migrations", cmd_migrate),
    ("Check System Status", cmd_status),
    ("Open Fixify in Browser", cmd_open),
    ("Exit", None),
]


def cmd_menu(args: list[str]) -> int:  # noqa: ARG001
    banner()
    while True:
        print()
        for number, (label, _) in enumerate(MENU, 1):
            print(f"  {cyan(f'[{number}]')} {label}")
        choice = _read_choice("Select an option")
        if choice is None:
            print()
            return 0
        if not choice.isdigit() or not 1 <= int(choice) <= len(MENU):
            print(f"  {yellow(f'Enter a number from 1 to {len(MENU)}.')}")
            continue
        label, handler = MENU[int(choice) - 1]
        if handler is None:
            return 0
        try:
            code = handler([])
        except KeyboardInterrupt:
            print()
            code = 130
        if code not in (0, None):
            print(f"\n  {dim(f'{label} finished with exit code {code}.')}")


COMMANDS: dict[str, Callable[[list[str]], int]] = {
    "start": cmd_start,
    "up": cmd_start,
    "infra": cmd_infra,
    "infrastructure": cmd_infra,
    "stop": cmd_stop,
    "down": cmd_stop,
    "restart": cmd_restart,
    "status": cmd_status,
    "logs": cmd_logs,
    "log": cmd_logs,
    "migrate": cmd_migrate,
    "open": cmd_open,
    "menu": cmd_menu,
    "help": cmd_help,
    "--help": cmd_help,
    "-h": cmd_help,
}


def main(argv: list[str]) -> int:
    if not argv:
        return cmd_menu([]) if _interactive() else cmd_help([])
    command, *rest = argv
    handler = COMMANDS.get(command.lower())
    if handler is None:
        print(red(f"Unknown command '{command}'."))
        cmd_help([])
        return 2
    if "--help" in rest or "-h" in rest:
        return cmd_help([])
    return handler(rest)


if __name__ == "__main__":
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, signal.default_int_handler)
    try:
        sys.exit(main(sys.argv[1:]))
    except KeyboardInterrupt:
        print()
        sys.exit(130)
