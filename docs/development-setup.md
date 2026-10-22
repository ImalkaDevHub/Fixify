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

Create future schema migrations with `alembic revision --autogenerate -m "description"` and apply using `alembic upgrade head`. Review generated migrations before applying them.
