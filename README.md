# Fixify

Fixify is a developer platform foundation for managing websites that will eventually be tested for bugs and offered human-reviewed fixes. This step delivers the application shell, persistent project management, and local infrastructure. It does **not** run scans, use AI, connect GitHub, or provide authentication.

> This is a local-development foundation. Do not expose it publicly until authentication, authorization, project ownership, rate limiting, and URL/SSRF protections are implemented.

## Current status

- Next.js App Router dashboard and project-management UI
- FastAPI `/api/v1` endpoints with async SQLAlchemy persistence
- PostgreSQL schema managed by Alembic
- PostgreSQL and Redis local containers
- Project create/list/detail/delete API and backend tests
- Readiness checks for PostgreSQL and Redis
- Browser scanning, AI analysis, GitHub OAuth, and user accounts are not implemented

## Architecture

- `apps/web`: strict TypeScript Next.js frontend; typed API client and validated project form
- `services/api`: FastAPI routers, Pydantic schemas, services, repositories, and SQLAlchemy models
- `infra`: local PostgreSQL and Redis Docker Compose services
- `docs`: architecture and local development instructions

See [docs/architecture.md](docs/architecture.md) and [docs/development-setup.md](docs/development-setup.md).

## Prerequisites

- Node.js 20.9+ and npm
- Python 3.12+ (Python 3.14 is also supported by the selected libraries)
- Docker Desktop or Docker Engine with Compose, or a native PostgreSQL installation

Check with `node --version`, `npm --version`, `python --version`, and `docker --version`.

## Quick start (Windows PowerShell)

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

In a second terminal, from the repository root:

```powershell
cd apps/web
Copy-Item .env.example .env.local
npm install
npm run dev
```

The dashboard is at <http://localhost:3000>. FastAPI interactive docs are at <http://localhost:8000/docs>; API health is <http://localhost:8000/api/v1/health>.

### macOS / Linux

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

In another terminal:

```bash
cd apps/web
cp .env.example .env.local
npm install
npm run dev
```

## Configuration

The root `.env.example` contains local placeholders. Copy it to `.env` and change the placeholder password before use. The frontend uses `apps/web/.env.local` copied from its `.env.example`; do not put secrets in `NEXT_PUBLIC_*` variables. Environment files are git-ignored.

If Docker is unavailable, install PostgreSQL locally, create a database and user matching `.env`, and run the API and web commands above. Redis can be installed locally or omitted from readiness checks by setting `REDIS_REQUIRED=false`; PostgreSQL is always required. Redis is reserved for future background work.

## Database migrations

After changing SQLAlchemy models, generate and inspect a migration:

```powershell
cd services/api
alembic revision --autogenerate -m "describe the schema change"
alembic upgrade head
```

To inspect the current migration revision, use `alembic current`. Do not use `create_all()` for application schema management.

## Checks

```powershell
# Backend (services/api; activate the virtual environment first)
pytest
ruff check .

# Frontend (apps/web)
npm run lint
npm run typecheck
npm run build
```

Backend tests use an isolated in-memory SQLite database and do not alter a developer database.

## Troubleshooting

- **Docker command not found:** install/start Docker Desktop, or use native PostgreSQL as described above.
- **Database connection refused:** ensure PostgreSQL is healthy with `docker compose --env-file .env -f infra/docker-compose.yml ps`; verify `DATABASE_URL`.
- **CORS error:** ensure `API_CORS_ORIGINS` includes the frontend origin and restart the API.
- **Frontend says API unavailable:** start FastAPI and confirm `NEXT_PUBLIC_API_BASE_URL` in `apps/web/.env.local`.
- **Migration has no database:** start PostgreSQL before `alembic upgrade head`.

## Manual project flow

1. Open <http://localhost:3000> and select **New project**.
2. Enter a project name and an HTTP(S) website URL; repository and branch are optional.
3. Submit, confirm the project appears in the list, and open its detail page.
4. Refresh the page to confirm the project persisted in PostgreSQL.

## Next stage

Add user identity and ownership before any public exposure, then implement URL/SSRF-safe browser scanning as an isolated worker, scan/run persistence, findings, and evidence-based reporting. Keep arbitrary browser execution out of the API process.
