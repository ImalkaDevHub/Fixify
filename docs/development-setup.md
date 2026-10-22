# Development setup

## Requirements

Install Node.js 20.9+, Python 3.12+ (tested on 3.14), and optionally Docker Compose. Verify with:

```powershell
node --version
npm --version
python --version
docker --version
docker compose version
```

Fixify runs three processes: the API, the browser worker, and the web app. PostgreSQL is always required. Redis is the default scan queue; without it, set `QUEUE_BACKEND=database`.

## Windows PowerShell

From the repository root:

```powershell
Copy-Item .env.example .env
docker compose --env-file .env -f infra/docker-compose.yml up -d

cd services/api
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m playwright install chromium
alembic upgrade head
uvicorn app.main:app --reload
```

Second terminal, the browser worker:

```powershell
cd services/api
.\.venv\Scripts\Activate.ps1
python -m app.worker
```

Third terminal:

```powershell
cd apps/web
Copy-Item .env.example .env.local
npm install
npm run dev
```

If PowerShell blocks virtual-environment activation, call the executables directly: `.\.venv\Scripts\python.exe -m pip install -e ".[dev]"`, `.\.venv\Scripts\python.exe -m playwright install chromium`, `.\.venv\Scripts\uvicorn.exe app.main:app --reload`, `.\.venv\Scripts\python.exe -m app.worker`.

Windows notes:

- Start the API with `--reload` as shown (or add `--loop asyncio:SelectorEventLoop`). Without either, uvicorn uses an event loop that psycopg's async mode cannot use and every database call fails. The worker chooses the correct loop itself.
- Compose publishes PostgreSQL on `127.0.0.1:5432`. If a native PostgreSQL service already owns that port, stop it first; otherwise `DATABASE_URL` reaches the wrong server.
- Interactive docs are at <http://localhost:8000/docs>, the dashboard at <http://localhost:3000>.

## macOS / Linux

```bash
cp .env.example .env
docker compose --env-file .env -f infra/docker-compose.yml up -d
cd services/api
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
python -m playwright install --with-deps chromium
alembic upgrade head
uvicorn app.main:app --reload
```

In another terminal run `python -m app.worker` from `services/api` with the virtual environment active. In a third, run `cd apps/web`, `cp .env.example .env.local`, `npm install`, and `npm run dev`.

## Browser installation

`python -m playwright install chromium` downloads the Chromium build matching the installed Playwright package (into `%LOCALAPPDATA%\ms-playwright` on Windows, `~/.cache/ms-playwright` on Linux). On Linux, `--with-deps` also installs the system libraries Chromium needs (it uses `sudo apt`). If a scan fails with "Executable doesn't exist", the browser was installed for a different Playwright version or a different environment: re-run the install command with the same `python` that runs the worker. Behind a proxy, set `HTTPS_PROXY` for the install command only.

## Browser worker in Docker

```powershell
docker compose --env-file .env -f infra/docker-compose.yml --profile worker up -d --build
```

The `worker` service uses `services/api/Dockerfile.worker` (official Playwright image, matching version), runs as the unprivileged `pwuser`, drops all capabilities, sets `no-new-privileges`, limits memory, CPU, and PIDs, publishes no ports, mounts no Docker socket, and mounts only `services/api/.artifacts` so the host API can serve screenshots. Run the API natively as above. This path has not been verified by a container build in this repository yet.

## Without Docker

Install PostgreSQL locally, create a database and user matching the environment values, and update `DATABASE_URL` in the root `.env`. Without Redis, set:

```env
QUEUE_BACKEND=database
REDIS_REQUIRED=false
```

Both the API and the worker must use the same values; the worker then picks up queued scans by polling PostgreSQL every `WORKER_POLL_INTERVAL_SECONDS`.

## Scanning a local test site

The scanner refuses `localhost` and private addresses. For a site you run locally during development, allow its exact address in the root `.env`, then restart the API and the worker:

```env
SCANNER_UNSAFE_ALLOWED_HOSTS=127.0.0.1:4100
```

The entry must match the host and port in the project URL exactly: `127.0.0.1:4100` allows `http://127.0.0.1:4100/` but not `http://localhost:4100/`. Leave the setting empty everywhere else.

## Checks and migrations

Run backend checks from `services/api` in the virtual environment using `pytest` and `ruff check .`. Scanner tests launch headless Chromium against a local fixture site and are skipped if Chromium is not installed. Run frontend checks from `apps/web` with `npm run lint`, `npm run typecheck`, and `npm run build`.

The migration test in `services/api/tests/test_migrations.py` runs only when `TEST_DATABASE_URL` points at a disposable PostgreSQL database whose name contains `test`; it applies all migrations, checks for model drift, and downgrades back to empty.

Create future schema migrations with `alembic revision --autogenerate -m "description"` and apply them with `alembic upgrade head`. Review generated migrations before applying them.
