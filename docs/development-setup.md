# Development setup

## Requirements

Install Node.js 20.9+, Python 3.12+, and Docker Compose. Python 3.14 is supported by the selected dependencies. Verify with:

```powershell
node --version
npm --version
python --version
docker --version
docker compose version
```

## Windows PowerShell

From the repository root:

```powershell
Copy-Item .env.example .env
docker compose --env-file .env -f infra/docker-compose.yml up -d

cd services/api
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
alembic upgrade head
uvicorn app.main:app --reload
```

Open a second terminal:

```powershell
cd apps/web
Copy-Item .env.example .env.local
npm install
npm run dev
```

If PowerShell blocks virtual-environment activation, use `.\.venv\Scripts\python.exe -m pip install -e ".[dev]"` and `.\.venv\Scripts\uvicorn.exe app.main:app --reload`.

Windows notes:

- Start the API with `--reload` as shown (or add `--loop asyncio:SelectorEventLoop`). Without either, uvicorn uses an event loop that psycopg's async mode cannot use and every database call fails.
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
alembic upgrade head
uvicorn app.main:app --reload
```

In another terminal run `cd apps/web`, `cp .env.example .env.local`, `npm install`, and `npm run dev`.

## Without Docker

Install PostgreSQL locally and create a database/user matching the environment values. Update `DATABASE_URL` in the root `.env`. Redis is not used for current features; for development without Redis set `REDIS_REQUIRED=false`. PostgreSQL remains required for readiness and project endpoints.

## Checks and migrations

Run backend checks from `services/api` in the virtual environment using `pytest` and `ruff check .`. Run frontend checks from `apps/web` with `npm run lint`, `npm run typecheck`, and `npm run build`.

The migration test in `services/api/tests/test_migrations.py` runs only when `TEST_DATABASE_URL` points at a disposable PostgreSQL database whose name contains `test`; it applies migrations, checks for model drift, and downgrades back to empty.

Create future schema migrations with `alembic revision --autogenerate -m "description"` and apply using `alembic upgrade head`. Review generated migrations before applying them.
