"""Read-only health probes for the Fixify launcher.

Runs inside the API virtual environment with ``services/api`` as the working directory, so it
reads configuration exactly the way the API and worker do (``app.core.config.settings``).

    python probe.py settings     configuration summary (never values of secrets)
    python probe.py db           connect to PostgreSQL and run SELECT 1
    python probe.py redis        PING Redis (skipped when the configuration does not need it)
    python probe.py migrations   compare the database revision with the Alembic head

Prints one JSON object on stdout. Exit code 0 = ok, 1 = check failed, 2 = probe error.
Nothing here writes to the database.
"""

from __future__ import annotations

import json
import sys
from urllib.parse import urlsplit

LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "0.0.0.0", ""}


def _emit(payload: dict, code: int) -> None:
    print(json.dumps(payload))
    sys.exit(code)


def _load_settings():
    """Import the app settings; report validation errors without echoing input values."""
    try:
        from app.core.config import settings
    except Exception as error:  # noqa: BLE001 - reported, not swallowed
        errors = getattr(error, "errors", None)
        if callable(errors):
            try:
                details = [
                    f"{'.'.join(str(part) for part in item.get('loc', ())) or 'settings'}: "
                    f"{item.get('msg', 'invalid')}"
                    for item in errors(include_input=False)
                ]
            except TypeError:
                details = [type(error).__name__]
        else:
            details = [f"{type(error).__name__}: {str(error).splitlines()[0][:200]}"]
        _emit({"ok": False, "error": "Configuration is invalid.", "details": details}, 1)
    return settings


def _host_info(url: str) -> dict:
    try:
        parts = urlsplit(url)
        host = parts.hostname or ""
        port = parts.port
    except ValueError:
        return {"host": "unparseable", "port": None, "local": False, "scheme": ""}
    return {
        "host": host,
        "port": port,
        "local": host in LOCAL_HOSTS,
        "scheme": parts.scheme.split("+")[0],
    }


def _sync_url(url: str) -> str:
    """The probes use a synchronous engine; psycopg serves both modes, aiosqlite does not."""
    return url.replace("sqlite+aiosqlite://", "sqlite://", 1)


def _scrub(message: str, *secrets: str | None) -> str:
    for secret in secrets:
        if secret:
            message = message.replace(secret, "****")
    return message.strip().splitlines()[0][:300] if message.strip() else "unknown error"


def _db_password(url: str) -> str | None:
    try:
        return urlsplit(url).password
    except ValueError:
        return None


ATTEMPTS = 3


def _retry(action):
    """Run ``action`` up to ATTEMPTS times: one dropped connection to a hosted database should
    not fail a whole start. Any error from the last attempt is raised."""
    import time

    for attempt in range(1, ATTEMPTS + 1):
        try:
            return action()
        except Exception:  # noqa: BLE001
            if attempt == ATTEMPTS:
                raise
            time.sleep(1.5 * attempt)
    return None


def probe_settings() -> None:
    settings = _load_settings()
    db = _host_info(settings.database_url)
    redis = _host_info(settings.redis_url)
    _emit(
        {
            "ok": True,
            "app_env": settings.app_env,
            "database": db,
            "database_is_default": settings.database_url
            == "postgresql+psycopg://fixify:change-me-locally@localhost:5432/fixify",
            "queue_backend": settings.queue_backend,
            "redis_needed": settings.redis_needed,
            "redis": redis,
            "public_app_url": settings.public_app_url,
            "ai_configured": bool(settings.ai_configured),
            "github_configured": bool(settings.github_configured),
            "email_backend": settings.email_backend,
            "secret_key_set": bool(
                getattr(settings.secret_key, "get_secret_value", lambda: settings.secret_key)()
            ),
            "is_production": settings.is_production,
        },
        0,
    )


def probe_db() -> None:
    settings = _load_settings()
    info = _host_info(settings.database_url)
    try:
        from sqlalchemy import create_engine, text

        connect_args = {}
        if info["scheme"] == "postgresql":
            connect_args["connect_timeout"] = settings.database_connect_timeout_seconds
        engine = create_engine(_sync_url(settings.database_url), connect_args=connect_args)

        sqlite = engine.dialect.name == "sqlite"

        def query() -> str:
            with engine.connect() as connection:
                sql = "SELECT sqlite_version()" if sqlite else "SELECT version()"
                return connection.execute(text(sql)).scalar() or ""

        try:
            version = _retry(query)
        finally:
            engine.dispose()
    except Exception as error:  # noqa: BLE001
        message = _scrub(
            str(getattr(error, "orig", None) or error), _db_password(settings.database_url)
        )
        _emit({"ok": False, "host": info["host"] or info["scheme"], "error": message}, 1)
    label = f"SQLite {version}" if sqlite else " ".join(version.split()[:2])
    _emit({"ok": True, "host": info["host"] or "local file", "version": label}, 0)


def probe_redis() -> None:
    settings = _load_settings()
    info = _host_info(settings.redis_url)
    if not settings.redis_needed:
        _emit({"ok": True, "skipped": True, "host": info["host"]}, 0)
    try:
        from redis import Redis

        client = Redis.from_url(settings.redis_url, socket_connect_timeout=3, socket_timeout=3)
        try:
            _retry(client.ping)
            version = client.info("server").get("redis_version", "")
        finally:
            client.close()
    except Exception as error:  # noqa: BLE001
        message = _scrub(str(error), _db_password(settings.redis_url))
        _emit({"ok": False, "host": info["host"], "error": message}, 1)
    _emit({"ok": True, "skipped": False, "host": info["host"], "version": version}, 0)


def probe_migrations() -> None:
    settings = _load_settings()
    try:
        from alembic.config import Config
        from alembic.runtime.migration import MigrationContext
        from alembic.script import ScriptDirectory
        from sqlalchemy import create_engine

        script = ScriptDirectory.from_config(Config("alembic.ini"))
        heads = list(script.get_heads())
        connect_args = {}
        if _host_info(settings.database_url)["scheme"] == "postgresql":
            connect_args["connect_timeout"] = settings.database_connect_timeout_seconds
        engine = create_engine(_sync_url(settings.database_url), connect_args=connect_args)

        def read_current() -> list[str]:
            with engine.connect() as connection:
                return list(MigrationContext.configure(connection).get_current_heads())

        try:
            current = _retry(read_current)
        finally:
            engine.dispose()
        pending: list[str] = []
        for head in heads:
            lower = current[0] if current else "base"
            for revision in script.iterate_revisions(head, lower):
                if revision.revision not in current:
                    pending.append(revision.revision)
        pending.reverse()
    except Exception as error:  # noqa: BLE001
        message = _scrub(
            str(getattr(error, "orig", None) or error), _db_password(settings.database_url)
        )
        _emit({"ok": False, "error": message}, 1)
    _emit({"ok": True, "current": current, "heads": heads, "pending": pending}, 0)


PROBES = {
    "settings": probe_settings,
    "db": probe_db,
    "redis": probe_redis,
    "migrations": probe_migrations,
}

if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in PROBES:
        _emit({"ok": False, "error": f"usage: probe.py {{{','.join(PROBES)}}}"}, 2)
    try:
        PROBES[sys.argv[1]]()
    except SystemExit:
        raise
    except Exception as error:  # noqa: BLE001
        _emit({"ok": False, "error": f"{type(error).__name__}: {str(error)[:200]}"}, 2)
