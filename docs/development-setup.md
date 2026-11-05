# Development setup (Windows PowerShell)

The quick start is in the [README](../README.md). This page covers the variations.

## Database options

| Option | `DATABASE_URL` |
|---|---|
| Docker Compose | `postgresql+psycopg://fixify:change-me-locally@localhost:5432/fixify` |
| Native PostgreSQL | Create a `fixify` database and user, then use the same format |
| Hosted (e.g. Supabase) | `postgresql+psycopg://USER:PASSWORD@HOST:5432/postgres?sslmode=require` |

After changing the database, run `alembic upgrade head` from `services/api`. Use `alembic check` to confirm the models match the migrations.

## Without Redis

```env
QUEUE_BACKEND=database
REDIS_REQUIRED=false
```

The worker then polls PostgreSQL. Rate limits fall back to the API process's memory.

## Running the processes

| Process | Command (from `services/api` with the venv active, or `apps/web`) |
|---|---|
| API | `python -m app.serve` (set `API_RELOAD=1` for auto-reload) |
| Worker | `python -m app.worker` (scans, AI and GitHub jobs, scheduler) |
| Web | `npm run dev` |

`python -m app.serve` always uses a selector event loop. Plain `uvicorn app.main:app` on Windows uses the Proactor loop, which async psycopg cannot use.

## Email in development

`EMAIL_BACKEND=console` prints verification and reset links in the **API** terminal. Copy the `http://localhost:3000/verify-email#token=…` link into the browser.

## Scanning a local site

`localhost` and private addresses are blocked on purpose. To scan a dev server on your machine, add its exact `host:port` to `SCANNER_UNSAFE_ALLOWED_HOSTS` for both the API and the worker (e.g. `127.0.0.1:4100`). Never set this in a shared environment; production refuses it.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `Psycopg cannot use the 'ProactorEventLoop'` | Start the API with `python -m app.serve` |
| Scan stays *Queued* | The worker is not running, or it uses another `.env` or `QUEUE_BACKEND` |
| 401 after restarting the API in development | With an empty `SECRET_KEY`, each API start uses a new random key. Set `SECRET_KEY` in `.env` to keep sessions across restarts |
| "Verify your email address first" | Use the link printed by the API (console email backend) or **Resend link** |
| AI or GitHub "not configured" | Set the keys described in [ai.md](ai.md) and [github-oauth.md](github-oauth.md), then restart the API and the worker |
| Frontend shows "Could not reach the Fixify API" | Start the API; check `API_INTERNAL_URL` in `apps/web/.env.local` (default `http://127.0.0.1:8000`) |
| Old projects are missing | `python -m app.cli assign-orphans --email you@example.com` |
