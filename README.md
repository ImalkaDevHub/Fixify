<div align="center">

# 🔧 Fixify

### Test websites for bugs. Get human-reviewed fixes.

A developer platform foundation for managing the websites you want tested, scanned, and fixed.

<br />

![Status](https://img.shields.io/badge/status-foundation-blueviolet?style=for-the-badge)
![Local only](https://img.shields.io/badge/use-local%20development-orange?style=for-the-badge)

![Next.js](https://img.shields.io/badge/Next.js-App%20Router-000000?style=flat-square&logo=nextdotjs&logoColor=white)
![TypeScript](https://img.shields.io/badge/TypeScript-strict-3178C6?style=flat-square&logo=typescript&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-async-009688?style=flat-square&logo=fastapi&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-Alembic-4169E1?style=flat-square&logo=postgresql&logoColor=white)
![Redis](https://img.shields.io/badge/Redis-ready-DC382D?style=flat-square&logo=redis&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?style=flat-square&logo=docker&logoColor=white)

[Quick start](#-quick-start) · [Architecture](#-architecture) · [Configuration](#-configuration) · [Troubleshooting](#-troubleshooting) · [Roadmap](#-roadmap)

</div>

---

> [!WARNING]
> **This is a local-development foundation.** Do not expose it publicly until authentication, authorization, project ownership, rate limiting, and URL/SSRF protections are implemented.

## ✨ What is Fixify?

Fixify is built to become a platform where you add a website, have it tested for bugs, and receive **human-reviewed fixes**. This first step delivers the solid ground everything else will stand on: the application shell, persistent project management, and local infrastructure.

## 📍 Current status

| | Feature | Status |
|---|---|---|
| 🖥️ | Next.js App Router dashboard and project-management UI | ✅ Ready |
| ⚡ | FastAPI `/api/v1` endpoints with async SQLAlchemy | ✅ Ready |
| 🐘 | PostgreSQL schema managed by Alembic | ✅ Ready |
| 🐳 | PostgreSQL and Redis local containers | ✅ Ready |
| 📁 | Project create / list / detail / delete API + backend tests | ✅ Ready |
| 🩺 | Readiness checks for PostgreSQL and Redis | ✅ Ready |
| 🕷️ | Browser scanning | ⏳ Not yet |
| 🤖 | AI analysis | ⏳ Not yet |
| 🐙 | GitHub OAuth | ⏳ Not yet |
| 👤 | User accounts and authentication | ⏳ Not yet |

## 🏗️ Architecture

```mermaid
flowchart LR
    U([👤 Developer]) --> W["🖥️ Next.js<br/>apps/web<br/>:3000"]
    W -->|typed API client| A["⚡ FastAPI<br/>services/api<br/>:8000"]
    A --> P[("🐘 PostgreSQL")]
    A -.->|readiness · future jobs| R[("🔴 Redis")]
```

Inside the API, each request flows through clean, separated layers:

```mermaid
flowchart LR
    Router["🛣️ Router"] --> Schema["📐 Pydantic schema"] --> Service["🧠 Service"] --> Repo["🗄️ Repository"] --> Model["📦 SQLAlchemy model"]
```

### Repository layout

```text
fixify/
├── apps/
│   └── web/           # Strict TypeScript Next.js frontend: typed API client, validated project form
├── services/
│   └── api/           # FastAPI routers, Pydantic schemas, services, repositories, SQLAlchemy models
├── infra/             # Local PostgreSQL + Redis via Docker Compose
└── docs/              # Architecture and local development instructions
```

📚 Read more in [docs/architecture.md](docs/architecture.md) and [docs/development-setup.md](docs/development-setup.md).

## 🧰 Prerequisites

| Tool | Version | Check with |
|---|---|---|
| Node.js + npm | 20.9+ | `node --version` · `npm --version` |
| Python | 3.12+ (3.14 also supported by the selected libraries) | `python --version` |
| Docker | Docker Desktop or Engine with Compose, *or* a native PostgreSQL install | `docker --version` |

## 🚀 Quick start

<details open>
<summary><b>🪟 Windows (PowerShell)</b></summary>

<br />

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

In a **second terminal**, from the repository root:

```powershell
cd apps/web
Copy-Item .env.example .env.local
npm install
npm run dev
```

</details>

<details>
<summary><b>🍎🐧 macOS / Linux</b></summary>

<br />

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

In **another terminal**:

```bash
cd apps/web
cp .env.example .env.local
npm install
npm run dev
```

</details>

### 🎉 You're live

| What | Where |
|---|---|
| 🖥️ Dashboard | <http://localhost:3000> |
| 📖 Interactive API docs | <http://localhost:8000/docs> |
| 💚 API health | <http://localhost:8000/api/v1/health> |

## 🧭 Try it: manual project flow

1. Open <http://localhost:3000> and select **New project**.
2. Enter a project name and an HTTP(S) website URL. Repository and branch are optional.
3. Submit, confirm the project appears in the list, and open its detail page.
4. Refresh the page to confirm the project persisted in PostgreSQL.

## ⚙️ Configuration

- The root `.env.example` contains local placeholders. Copy it to `.env` and **change the placeholder password** before use.
- The frontend uses `apps/web/.env.local`, copied from its own `.env.example`.
- 🔐 **Never put secrets in `NEXT_PUBLIC_*` variables.**
- Environment files are git-ignored.

<details>
<summary><b>No Docker? Use native PostgreSQL</b></summary>

<br />

Install PostgreSQL locally, create a database and user matching `.env`, then run the API and web commands above. Redis can be installed locally, or omitted from readiness checks by setting:

```env
REDIS_REQUIRED=false
```

PostgreSQL is **always** required. Redis is reserved for future background work.

> [!NOTE]
> Website URL validation checks syntax and the HTTP/HTTPS scheme only. It does **not** make scanning arbitrary URLs safe; SSRF protection is a prerequisite for any scanner.

</details>

## 🗃️ Database migrations

After changing SQLAlchemy models, generate and inspect a migration:

```powershell
cd services/api
alembic revision --autogenerate -m "describe the schema change"
alembic upgrade head
```

Check the current revision with `alembic current`.

> [!IMPORTANT]
> Do not use `create_all()` for application schema management. Alembic owns the schema.

## ✅ Checks

| Area | Directory | Commands |
|---|---|---|
| 🐍 Backend | `services/api` *(activate the virtual environment first)* | `pytest` · `ruff check .` |
| 🟦 Frontend | `apps/web` | `npm run lint` · `npm run typecheck` · `npm run build` |

Backend tests use an isolated in-memory SQLite database and never touch your developer database. SQLite cannot prove PostgreSQL behavior, so the Alembic migration test in `tests/test_migrations.py` is skipped unless you point `TEST_DATABASE_URL` at a **disposable PostgreSQL database whose name contains `test`** (it applies the migrations, checks for model drift, then downgrades to empty):

```powershell
$env:TEST_DATABASE_URL = "postgresql+psycopg://USER:PASSWORD@localhost:5432/fixify_migration_test"
pytest tests/test_migrations.py
```

## 🩹 Troubleshooting

| Symptom | Fix |
|---|---|
| **Docker command not found** | Install/start Docker Desktop, or use native PostgreSQL as described above. |
| **Database connection refused** | Check health with `docker compose --env-file .env -f infra/docker-compose.yml ps` and verify `DATABASE_URL`. |
| **CORS error** | Make sure `API_CORS_ORIGINS` includes the frontend origin, then restart the API. |
| **Frontend says API unavailable** | Start FastAPI and confirm `NEXT_PUBLIC_API_BASE_URL` in `apps/web/.env.local`. |
| **Migration has no database** | Start PostgreSQL before running `alembic upgrade head`. |
| **Port 5432 already in use / wrong credentials** | A native PostgreSQL service on the same machine already owns port 5432, so the Compose container cannot bind it and `DATABASE_URL` would reach the wrong server. Stop the native service, or use it deliberately by creating the `fixify` database and user there. |
| **`Psycopg cannot use the 'ProactorEventLoop'` (Windows)** | Run the API with `--reload` (as documented) or add `--loop asyncio:SelectorEventLoop`. Plain `uvicorn app.main:app` on Windows uses an event loop psycopg cannot use. |
| **Readiness takes ~5 s then returns 503** | PostgreSQL is unreachable; the connection attempt gives up after `DATABASE_CONNECT_TIMEOUT_SECONDS` (default 5). |

## 🗺️ Roadmap

- [x] Application shell and project management (create / list / detail / delete)
- [x] Async persistence with PostgreSQL + Alembic migrations
- [x] Local infrastructure and readiness checks
- [ ] 👤 User identity and project ownership *(required before any public exposure)*
- [ ] 🛡️ URL / SSRF-safe validation and rate limiting
- [ ] 🕷️ Browser scanning as an **isolated worker**, never inside the API process
- [ ] 🧾 Scan and run persistence
- [ ] 🐞 Findings
- [ ] 📊 Evidence-based reporting
- [ ] 🧑‍🔧 Human-reviewed fixes

<div align="center">

<br />

**Built step by step, safely first. 🔧**

</div>
