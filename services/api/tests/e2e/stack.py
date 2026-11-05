"""END-TO-END TEST HARNESS ONLY. Never use for real data.

Runs the real FastAPI app, scan worker, and job worker in one process, but against:
  * a throwaway SQLite database (``--data``, default: a temporary directory), or, with
    ``--database-url``, a disposable PostgreSQL database whose name contains "test" (schema
    created by the real Alembic migrations; ``--redis-url`` adds the real Redis queue),
  * a scripted mock AI provider (clearly labelled "mock-e2e" in the UI),
  * an in-memory fake GitHub API plus a tiny fake authorization page,
  * the scanner's local fixture website as the scan target.

This exercises the whole workflow (scan, analysis, GitHub connection, fix, review, branch,
commit, pull request) in a real browser when no AI key or GitHub OAuth app is available.

    python -m tests.e2e.stack            # then open http://localhost:3000 (npm run dev)
    python -m tests.e2e.stack --redis-url redis://127.0.0.1:6379/15 \
        --database-url postgresql+psycopg://USER:PASSWORD@127.0.0.1:5433/fixify_e2e_test

The web app must point at this API (API_INTERNAL_URL, default http://127.0.0.1:8000).
"""

import argparse
import asyncio
import os
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit

FAKE_GITHUB_PORT = 8766


def _configure(
    data_dir: Path, fixture_port: int, database_url: str | None, redis_url: str | None
) -> None:
    from cryptography.fernet import Fernet

    os.environ.update(
        {
            "FIXIFY_IGNORE_ENV_FILE": "1",
            "APP_ENV": "development",
            "DATABASE_URL": database_url
            or f"sqlite+aiosqlite:///{(data_dir / 'e2e.sqlite').as_posix()}",
            "QUEUE_BACKEND": "redis" if redis_url else "database",
            "REDIS_REQUIRED": "true" if redis_url else "false",
            "REDIS_URL": redis_url or "redis://127.0.0.1:6379/0",
            "WORKER_POLL_INTERVAL_SECONDS": "1",
            "SECRET_KEY": "e2e-harness-only-" + "x" * 32,
            "PUBLIC_APP_URL": "http://localhost:3000",
            "EMAIL_BACKEND": "console",
            "ARTIFACT_DIR": str(data_dir / "artifacts"),
            "SCANNER_ALLOWED_PORTS": f"80,443,{fixture_port}",
            "SCANNER_UNSAFE_ALLOWED_HOSTS": f"127.0.0.1:{fixture_port}",
            "AI_PROVIDER": "anthropic",
            "ANTHROPIC_API_KEY": "mock-e2e-not-a-real-key",
            "AI_MODEL": "mock-e2e (test harness)",
            "GITHUB_CLIENT_ID": "e2e-client",
            "GITHUB_CLIENT_SECRET": "e2e-secret",
            "TOKEN_ENCRYPTION_KEY": Fernet.generate_key().decode(),
            "GITHUB_WEB_URL": f"http://127.0.0.1:{FAKE_GITHUB_PORT}",
        }
    )


class _AuthorizePage(BaseHTTPRequestHandler):
    """Stands in for github.com/login/oauth/authorize: approves immediately."""

    def log_message(self, *_args: object) -> None:
        return

    def do_GET(self) -> None:  # noqa: N802
        query = parse_qs(urlsplit(self.path).query)
        redirect = query.get("redirect_uri", [""])[0]
        if not redirect.startswith("http://localhost:3000/"):
            self.send_response(400)
            self.end_headers()
            return
        target = redirect + "?" + urlencode({"code": "good-code", "state": query["state"][0]})
        self.send_response(302)
        self.send_header("Location", target)
        self.end_headers()


class MockProvider:
    """Deterministic AI stand-in. Output is plausible but clearly labelled as a mock."""

    name = "mock-e2e"
    model = "mock-e2e (test harness)"

    async def generate_json(self, *, system, user_content, schema, max_tokens):
        from app.ai.provider import AIResult
        from tests.platform_fakes import analysis_output, fix_output

        await asyncio.sleep(1.5)  # long enough to see the "working" state in the UI
        if "edits" in schema.get("properties", {}):
            data = fix_output(
                title="Add a page title to index.html",
                explanation="[MOCK AI] Adds a <title> element to the document head so browsers "
                "and search engines can name the page.",
            )
        else:
            data = analysis_output(
                summary="[MOCK AI] The page has no <title>, so tabs and bookmarks show the URL.",
            )
        return AIResult(
            data=data,
            provider=self.name,
            model=self.model,
            input_tokens=len(user_content) // 4,
            output_tokens=200,
        )


class FileOutbox:
    """Writes outgoing email to <data>/outbox.jsonl so automated tests can follow links."""

    def __init__(self, path: Path) -> None:
        self.path = path

    async def send(self, message) -> None:
        import json

        with self.path.open("a", encoding="utf-8") as handle:
            record = {"to": message.to, "subject": message.subject, "text": message.text}
            handle.write(json.dumps(record) + "\n")


async def _run(port: int, data_dir: Path) -> None:
    import uvicorn
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import app.db.session as db_session
    from app.core.config import settings
    from app.core.email import get_email_sender
    from app.db import models  # noqa: F401
    from app.db.base import Base
    from app.main import app
    from app.services import github as github_service
    from app.worker.jobs import JobWorker
    from app.worker.main import ScanWorker
    from app.worker.queue import create_queue
    from tests.platform_fakes import FakeGitHub

    postgres = settings.database_url.startswith("postgresql")
    if postgres:  # the real migrations, exactly as production applies them
        migrated = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=Path(__file__).resolve().parents[2],
            capture_output=True,
            text=True,
            timeout=180,
        )
        if migrated.returncode != 0:
            raise SystemExit(f"alembic upgrade head failed:\n{migrated.stderr[-1500:]}")
    engine = create_async_engine(settings.database_url)
    if not postgres:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    db_session.SessionFactory = factory  # get_session reads this at request time

    fake_github = FakeGitHub()
    github_service.transport = fake_github.transport()
    provider = MockProvider()
    outbox = FileOutbox(data_dir / "outbox.jsonl")
    app.dependency_overrides[get_email_sender] = lambda: outbox

    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    backend = "PostgreSQL" if postgres else "SQLite"
    queue = f"{settings.queue_backend} queue"
    print(
        f"E2E harness API on http://127.0.0.1:{port} (mock AI, fake GitHub, {backend}, {queue})",
        flush=True,
    )
    await asyncio.gather(
        server.serve(),
        ScanWorker(settings, factory, create_queue(settings)).run_forever(),
        JobWorker(settings, factory, lambda: provider).run_forever(),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--data", type=Path, default=None)
    parser.add_argument(
        "--database-url",
        default=None,
        help="disposable PostgreSQL database; its name must contain 'test'",
    )
    parser.add_argument("--redis-url", default=None, help="use the Redis queue (e.g. db 15)")
    args = parser.parse_args()
    if args.database_url:
        from sqlalchemy.engine import make_url

        if "test" not in (make_url(args.database_url).database or "").lower():
            parser.error("Refusing to use a database whose name does not contain 'test'.")
    data_dir = args.data or Path(tempfile.mkdtemp(prefix="fixify-e2e-"))
    data_dir.mkdir(parents=True, exist_ok=True)

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from tests.fixtures.scan_site import serve_site

    authorize = ThreadingHTTPServer(("127.0.0.1", FAKE_GITHUB_PORT), _AuthorizePage)
    threading.Thread(target=authorize.serve_forever, daemon=True).start()
    with serve_site() as (site_url, _blocked):
        fixture_port = int(urlsplit(site_url).port or 0)
        _configure(data_dir, fixture_port, args.database_url, args.redis_url)
        print(f"Scan target (fixture site): {site_url}/no-title", flush=True)
        (data_dir / "harness.json").write_text(
            __import__("json").dumps({"site_url": site_url, "api_port": args.port}),
            encoding="utf-8",
        )
        print(f"Data directory: {data_dir}", flush=True)
        loop_factory = asyncio.SelectorEventLoop if sys.platform == "win32" else None
        try:
            asyncio.run(_run(args.port, data_dir), loop_factory=loop_factory)
        except KeyboardInterrupt:
            pass
        finally:
            authorize.shutdown()


if __name__ == "__main__":
    main()
