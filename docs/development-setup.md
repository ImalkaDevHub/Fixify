# Development setup

The quick start is in the [README](../README.md). This page covers the database, Redis, data import, and the variations.

## Architecture (local)

| Component | Runs as | Notes |
|---|---|---|
| PostgreSQL 17 | Docker Compose service `postgres` | Self-managed. Persistent volume `postgres_data`. Bound to `127.0.0.1` only |
| Redis 7 | Docker Compose service `redis` | Scan queue (default) and shared rate limits. Persistent volume `redis_data` (append-only file) |
| API (FastAPI) | host process `python -m app.serve` | Enqueues scans and never runs a browser |
| Worker | host process `python -m app.worker` | Scans (Playwright + Chromium in a separate scanner process), AI and GitHub jobs, scheduler |
| Web (Next.js) | host process `next dev` | Proxies `/api/v1/*` to the API (same origin) |

`.\fixify.ps1 start` (or `./fixify.sh start`) runs all of this in order with health checks. See [Local launcher](../README.md#local-launcher).

## Database

Compose creates the database from `POSTGRES_DB`, `POSTGRES_USER` and `POSTGRES_PASSWORD` in the root `.env`. `DATABASE_URL` must use the same values:

```env
POSTGRES_DB=fixify
POSTGRES_USER=fixify_user
POSTGRES_PASSWORD=<a long random local password>
POSTGRES_HOST_PORT=5432
DATABASE_URL=postgresql+psycopg://fixify_user:<same password>@127.0.0.1:5432/fixify
```

Generate a password with `python -c "import secrets; print(secrets.token_urlsafe(24))"`.

* **Driver:** `postgresql+psycopg` is psycopg 3, used in async mode by the API and worker and in sync mode by Alembic. Fixify does not use `asyncpg`, so a `postgresql+asyncpg://` URL will not work.
* **Port already in use:** if a native PostgreSQL already listens on 5432, set `POSTGRES_HOST_PORT=5433` and use `127.0.0.1:5433` in `DATABASE_URL`. `REDIS_HOST_PORT` does the same for Redis.
* **Credentials are fixed when the volume is created.** Changing `POSTGRES_PASSWORD` later does not change an existing database's password. Change it with `ALTER USER`, or create the database fresh under a new Compose project name. Do **not** remove the volume to reset a password; that deletes the data.
* **Migrations:** `.\fixify.ps1 migrate`, or `alembic upgrade head` from `services/api`. Migrations are forward-only and additive; `alembic check` confirms the models match them.
* A native PostgreSQL install also works: create the database and user, point `DATABASE_URL` at it, and the launcher will not start a container.

### Importing data from an earlier database

The development data used to live in a hosted database. Fixify no longer depends on it. A **read-only export** of its `public` schema (Fixify's tables) can be taken with `pg_dump` and restored into the local database. Nothing on the old server is changed.

```powershell
# 1. Export (read-only on the old server). Pass the password through PGPASSWORD, never on the command line.
$env:PGPASSWORD = '<old password>'; $env:PGSSLMODE = 'require'
& 'C:\Program Files\PostgreSQL\18\bin\pg_dump.exe' --host <old host> --port 5432 --username <old user> `
    --dbname postgres --schema public --format custom --no-owner --no-privileges `
    --file backups\old-public.dump
Remove-Item Env:PGPASSWORD

# 2. Restore into an EMPTY local database (before running the app against it).
$env:PGPASSWORD = '<local password>'
& 'C:\Program Files\PostgreSQL\18\bin\pg_restore.exe' --host localhost --port 5433 --username fixify_user `
    --dbname fixify --no-owner --no-privileges --exit-on-error backups\old-public.dump
Remove-Item Env:PGPASSWORD

# 3. Confirm the schema version, then start Fixify.
.\fixify.ps1 migrate
```

* `backups/` is git-ignored. Exports contain account data (emails, password hashes, encrypted tokens): keep them private.
* Restore into an empty database, so restored rows never collide with new ones. If the local database already has data, restore into a new database (for example `fixify_imported`) and point `DATABASE_URL` at it instead.
* Screenshots are files, not database rows. They stay in the old artifact folder (`services/api/.artifacts`). The local database uses `ARTIFACT_DIR=.artifacts-local`, so neither database's cleanup ever touches the other's files.
* GitHub tokens in the export are encrypted with the old `TOKEN_ENCRYPTION_KEY`. Without that key, users simply reconnect GitHub.

## Redis

Redis is the intended default queue (`QUEUE_BACKEND=redis`, `REDIS_REQUIRED=true`). PostgreSQL stays the source of truth: Redis only announces run IDs, the worker claims runs atomically in PostgreSQL, and a periodic database sweep picks up anything a lost message never announced.

`QUEUE_BACKEND=database` with `REDIS_REQUIRED=false` is a fallback for machines without Docker or Redis. The worker then polls PostgreSQL, and rate limits are kept per API process instead of shared. Both modes are covered by the test suite.

## Running the processes by hand

| Process | Command (from `services/api` with the venv active, or `apps/web`) |
|---|---|
| Infrastructure | `docker compose --env-file .env -f infra/docker-compose.yml up -d postgres redis` (from the repository root) |
| API | `python -m app.serve` (set `API_RELOAD=1` for auto-reload) |
| Worker | `python -m app.worker` (scans, AI and GitHub jobs, scheduler) |
| Web | `npm run dev` |

`python -m app.serve` always uses a selector event loop. Plain `uvicorn app.main:app` on Windows uses the Proactor loop, which async psycopg cannot use.

The worker stops cleanly on Ctrl+C, SIGTERM (`docker stop`), and Ctrl+Break on Windows: scanners are stopped and in-flight scans are handed back to the queue. If the database is briefly unreachable, the worker logs a warning and retries with backoff (2 s up to 30 s) instead of exiting.

## Email in development

`EMAIL_BACKEND=console` writes verification and reset links to the **API** log (`.\fixify.ps1 logs api`). Copy the `http://localhost:3000/verify-email#token=…` link into the browser.

## Scanning a local site

`localhost` and private addresses are blocked on purpose (SSRF protection). To scan a dev server on your machine, add its exact `host:port` to `SCANNER_UNSAFE_ALLOWED_HOSTS` for both the API and the worker (for example `127.0.0.1:4100`). Never set this in a shared environment; production refuses it.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `Psycopg cannot use the 'ProactorEventLoop'` | Start the API with `python -m app.serve` |
| `password authentication failed for user "fixify_user"` | The volume was created with a different `POSTGRES_PASSWORD`; see "Credentials are fixed" above |
| `port 5432 is already used by another process` | A native PostgreSQL is running: set `POSTGRES_HOST_PORT=5433` and update `DATABASE_URL` |
| Scan stays *Queued* | The worker is not running, or it uses another `.env` or `QUEUE_BACKEND` |
| 401 after restarting the API in development | With an empty `SECRET_KEY`, each API start uses a new random key. Set `SECRET_KEY` in `.env` |
| "Verify your email address first" | Use the link in the API log (console email backend) or **Resend link** |
| AI or GitHub "not configured" | Set the keys described in [ai.md](ai.md) and [github-oauth.md](github-oauth.md), then restart the API and the worker |
| Frontend shows "Could not reach the Fixify API" | Start the API; check `API_INTERNAL_URL` (default `http://127.0.0.1:8000`) |
| Old projects are missing | `python -m app.cli assign-orphans --email you@example.com` |
