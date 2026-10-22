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
> **Local development only.** There is no authentication, authorization, or project ownership: anyone who can reach the API can start scans and read every result. The scanner blocks private and internal network destinations (see [docs/scanner.md](docs/scanner.md)), but that is not a substitute for access control. Do not expose Fixify publicly, and only scan websites you are authorized to test.

## ✨ What is Fixify?

Fixify is built to become a platform where you add a website, have it tested for bugs, and receive **human-reviewed fixes**. Step 1 delivered the application shell, project management, and local infrastructure. **Step 2 adds a real, rule-based browser scanner**: a separate worker opens your website in headless Chromium, records the errors it actually observes, and stores the results and a screenshot in PostgreSQL. There is no AI in this step.

## 📍 Current status

| | Feature | Status |
|---|---|---|
| 🖥️ | Next.js App Router dashboard and project-management UI | ✅ Ready |
| ⚡ | FastAPI `/api/v1` endpoints with async SQLAlchemy | ✅ Ready |
| 🐘 | PostgreSQL schema managed by Alembic | ✅ Ready |
| 🐳 | PostgreSQL and Redis local containers | ✅ Ready |
| 📁 | Project create / list / detail / delete API + backend tests | ✅ Ready |
| 🩺 | Readiness checks for PostgreSQL and the scan queue | ✅ Ready |
| 🕷️ | Playwright scanner in a separate worker process (8 rule-based checks) | ✅ Ready |
| 🛡️ | SSRF policy enforced on every browser and link-checker connection | ✅ Ready (see limits) |
| 📊 | Scan history, reports, findings, screenshots, scan comparison | ✅ Ready |
| 🤖 | AI test generation / analysis | ⏳ Not yet |
| 🐙 | GitHub OAuth | ⏳ Not yet |
| 👤 | User accounts and authentication | ⏳ Not yet |

## 🏗️ Architecture

```mermaid
flowchart LR
    U([👤 Developer]) --> W["🖥️ Next.js<br/>apps/web<br/>:3000"]
    W -->|typed API client| A["⚡ FastAPI<br/>services/api<br/>:8000"]
    A --> P[("🐘 PostgreSQL")]
    A -->|run ID| R[("🔴 Redis queue")]
    R --> K["🧵 Worker<br/>python -m app.worker"]
    K <-->|claim · results| P
    K -->|job JSON, no DB/Redis env| S["🕷️ Scanner process<br/>python -m app.scanner"]
    S --> X["🛡️ Egress proxy<br/>URL policy"] --> C["🌐 Headless Chromium"]
    X --> Web(("Website"))
```

The API never runs a browser. It validates the request, creates a `queued` run, and returns `202`. The worker claims the run atomically, starts the scanner as a **separate process with a stripped environment** (no database or Redis credentials), and stores the result in one transaction. All browser and link-check traffic goes through a local proxy that enforces the URL safety policy. Details: [docs/scanner.md](docs/scanner.md).

Inside the API, each request flows through clean, separated layers:

```mermaid
flowchart LR
    Router["🛣️ Router"] --> Schema["📐 Pydantic schema"] --> Service["🧠 Service"] --> Repo["🗄️ Repository"] --> Model["📦 SQLAlchemy model"]
```

### Repository layout

```text
fixify/
├── apps/
│   └── web/           # Next.js frontend: dashboard, projects, scan reports, findings
├── services/
│   └── api/
│       ├── app/api/v1/      # FastAPI routers (projects, scans, findings, artifacts, health)
│       ├── app/scanner/     # Isolated scanner: URL policy, egress proxy, Playwright engine, checks
│       ├── app/worker/      # Queue, worker loop, scanner subprocess executor, result persistence
│       ├── alembic/         # Migrations (0001 projects, 0002 scans)
│       └── tests/           # pytest: API, worker lifecycle, SSRF policy, real-browser scanner
├── infra/             # Docker Compose: PostgreSQL, Redis, optional browser worker
└── docs/              # Architecture, scanner, and development setup
```

📚 Read more in [docs/architecture.md](docs/architecture.md), [docs/scanner.md](docs/scanner.md), and [docs/development-setup.md](docs/development-setup.md).

## 🧰 Prerequisites

| Tool | Version | Check with |
|---|---|---|
| Node.js + npm | 20.9+ | `node --version` · `npm --version` |
| Python | 3.12+ (tested on 3.14) | `python --version` |
| Docker | Docker Desktop or Engine with Compose, *or* native PostgreSQL | `docker --version` |
| Chromium for Playwright | installed by `python -m playwright install chromium` | — |

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
python -m playwright install chromium
alembic upgrade head
uvicorn app.main:app --reload
```

In a **second terminal** (the browser worker), from the repository root:

```powershell
cd services/api
.\.venv\Scripts\Activate.ps1
python -m app.worker
```

In a **third terminal**, from the repository root:

```powershell
cd apps/web
Copy-Item .env.example .env.local
npm install
npm run dev
```

No Redis? Set `QUEUE_BACKEND=database` in the root `.env` (read by both the API and the worker); the worker then polls PostgreSQL for queued scans.

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
python -m playwright install --with-deps chromium
alembic upgrade head
uvicorn app.main:app --reload
```

In **another terminal**: `cd services/api && source .venv/bin/activate && python -m app.worker`.

In **a third terminal**:

```bash
cd apps/web
cp .env.example .env.local
npm install
npm run dev
```

</details>

<details>
<summary><b>🐳 Browser worker in Docker (optional)</b></summary>

<br />

The worker can run in a container built from the official Playwright image, with dropped capabilities, memory/CPU/PID limits, no published ports, and only the artifact folder mounted. The API still runs on the host and serves screenshots from `services/api/.artifacts`.

```powershell
docker compose --env-file .env -f infra/docker-compose.yml --profile worker up -d --build
docker compose --env-file .env -f infra/docker-compose.yml logs -f worker
```

This container path has not been verified by an actual build yet.

</details>

### 🎉 You're live

| What | Where |
|---|---|
| 🖥️ Dashboard | <http://localhost:3000> |
| 📖 Interactive API docs | <http://localhost:8000/docs> |
| 💚 API readiness | <http://localhost:8000/api/v1/health/ready> |

## 🧭 Try it: your first scan

1. Open <http://localhost:3000> and select **New project**.
2. Enter a name and the HTTP(S) URL of a website **you are authorized to test**.
3. On the project page, select **Run scan**. The status goes *Queued* → *Running* → *Completed* (usually 5–30 s).
4. Open the scan report: checks, findings by severity, the screenshot, and a comparison with the previous scan.
5. Open a finding to see its sanitized evidence. Refresh: everything is stored in PostgreSQL.

`localhost`, private, and internal addresses are refused on purpose. To scan a site on your own machine during development, add its exact `host:port` to `SCANNER_UNSAFE_ALLOWED_HOSTS` for the API **and** the worker (for example `127.0.0.1:4100`). Never set this in a shared environment.

## 🕷️ What the scanner checks

| Check | Reports |
|---|---|
| Page navigation | Final URL, HTTP status, redirects, duration; timeouts, unreachable sites, and error status pages (a 404/5xx is a failure even though Chromium renders a page) |
| JavaScript console errors | Distinct `console.error` messages (warnings are ignored) |
| Uncaught exceptions | Page errors with a bounded stack trace |
| Failed network requests | Network-level failures; cancellations (`net::ERR_ABORTED`) are ignored |
| HTTP error responses | Sub-resources with 4xx/5xx; severity depends on resource type and first- vs third-party |
| Broken links | Up to `SCANNER_MAX_LINKS` unique HTTP(S) links; only 404/410 are *confirmed*, 5xx and DNS failures are *suspected*, 401/403/429/timeouts are *inconclusive* and not reported as bugs |
| Screenshot | One viewport-sized PNG (not full page), size-limited |
| Basic page checks | Missing title, `<h1>`, viewport meta, favicon. Indicators only: **not** an accessibility or SEO audit |

Severity rules, what evidence is (and is not) stored, and the security boundaries are in [docs/scanner.md](docs/scanner.md).

## ⚙️ Configuration

- The root `.env.example` contains local placeholders. Copy it to `.env` and **change the placeholder password** before use. The API, the worker, and Compose read it.
- `services/api/.env.example` lists every backend and scanner setting with its default.
- The frontend uses `apps/web/.env.local`, copied from its own `.env.example`.
- 🔐 **Never put secrets in `NEXT_PUBLIC_*` variables.** Environment files are git-ignored.

| Setting | Default | Notes |
|---|---|---|
| `QUEUE_BACKEND` | `redis` | `database` = no Redis; the worker polls PostgreSQL |
| `ARTIFACT_DIR` | `services/api/.artifacts` | Screenshots; git-ignored |
| `ARTIFACT_RETENTION_DAYS` | `14` | The worker deletes older screenshot folders hourly |
| `SCANNER_MAX_SCAN_DURATION_SECONDS` | `180` | Hard cap 900; the worker kills the scanner 30 s after this |
| `SCANNER_NAVIGATION_TIMEOUT_SECONDS` | `30` | Hard cap 120 |
| `SCANNER_MAX_LINKS` / `SCANNER_LINK_CONCURRENCY` | `25` / `4` | Hard caps 200 / 10 |
| `SCANNER_ALLOWED_PORTS` | `80,443,8080,8443` | Other ports are blocked |
| `SCANNER_UNSAFE_ALLOWED_HOSTS` | empty | Development fixtures only |
| `WORKER_CONCURRENCY` / `SCAN_MAX_ATTEMPTS` | `1` / `2` | Parallel scans per worker / attempts after a crash |

<details>
<summary><b>No Docker? Use native PostgreSQL</b></summary>

<br />

Install PostgreSQL locally, create a database and user matching `.env`, then run the commands above with:

```env
QUEUE_BACKEND=database
REDIS_REQUIRED=false
```

PostgreSQL is **always** required.

</details>

## 🗃️ Database migrations

```powershell
cd services/api
alembic upgrade head
alembic current
```

After changing SQLAlchemy models, generate a migration with `alembic revision --autogenerate -m "describe the change"` and review it before applying.

> [!IMPORTANT]
> Do not use `create_all()` for application schema management. Alembic owns the schema.

## ✅ Checks

| Area | Directory | Commands |
|---|---|---|
| 🐍 Backend | `services/api` *(activate the virtual environment first)* | `pytest` · `ruff check .` |
| 🟦 Frontend | `apps/web` | `npm run lint` · `npm run typecheck` · `npm run build` |

Backend tests use an isolated in-memory SQLite database and fake DNS; they never touch your developer database or the internet. The scanner tests drive real headless Chromium against a local fixture website (`tests/fixtures/scan_site.py`) and are skipped if Chromium is not installed. SQLite cannot prove PostgreSQL behavior, so the Alembic migration test in `tests/test_migrations.py` runs only when `TEST_DATABASE_URL` points at a **disposable PostgreSQL database whose name contains `test`**:

```powershell
$env:TEST_DATABASE_URL = "postgresql+psycopg://USER:PASSWORD@localhost:5432/fixify_migration_test"
pytest tests/test_migrations.py
```

## 🩹 Troubleshooting

| Symptom | Fix |
|---|---|
| **Scan stays *Queued*** | The worker is not running, or it uses a different `QUEUE_BACKEND` or database than the API. Start `python -m app.worker` from `services/api` with the same `.env`. |
| **"This URL cannot be scanned"** | The target resolves to a private/local address, uses a blocked port, or is a single-label/internal name. This is the SSRF policy working. For local test sites see `SCANNER_UNSAFE_ALLOWED_HOSTS`. |
| **Scan *Failed*: "Scanner process failed"** | Check the worker log. Usually Chromium is missing: run `python -m playwright install chromium` (Linux: add `--with-deps`). |
| **`Executable doesn't exist ... ms-playwright`** | Same as above; the Playwright package and its browser build must be installed in the same environment. |
| **Screenshot missing in the report** | The file was removed by the retention policy, or it exceeded `ARTIFACT_MAX_BYTES`. |
| **Docker command not found** | Install/start Docker Desktop, or use native PostgreSQL with `QUEUE_BACKEND=database`. |
| **Database connection refused** | Check `docker compose --env-file .env -f infra/docker-compose.yml ps` and verify `DATABASE_URL`. |
| **CORS error** | Make sure `API_CORS_ORIGINS` includes the frontend origin, then restart the API. |
| **Frontend says API unavailable** | Start FastAPI and confirm `NEXT_PUBLIC_API_BASE_URL` in `apps/web/.env.local`. |
| **Port 5432 already in use / wrong credentials** | A native PostgreSQL service already owns port 5432, so the Compose container cannot bind it and `DATABASE_URL` reaches the wrong server. Stop the native service, or create the `fixify` database and user there. |
| **`Psycopg cannot use the 'ProactorEventLoop'` (Windows)** | Run the API with `--reload` or add `--loop asyncio:SelectorEventLoop`. The worker selects the right loop itself. |
| **Readiness takes ~5 s then returns 503** | PostgreSQL (or Redis, with `QUEUE_BACKEND=redis`) is unreachable. |

## 🗺️ Roadmap

- [x] Application shell and project management (create / list / detail / delete)
- [x] Async persistence with PostgreSQL + Alembic migrations
- [x] Local infrastructure and readiness checks
- [x] 🕷️ Browser scanning in a separate worker and scanner process, never inside the API
- [x] 🛡️ URL / SSRF policy for every scanner connection (limitations in docs/scanner.md)
- [x] 🧾 Scan runs, check results, findings, screenshots, scan comparison
- [ ] 👤 User identity, project ownership, rate limiting *(required before any public exposure)*
- [ ] 🤖 AI-generated test cases and explanations
- [ ] 🐙 GitHub integration
- [ ] 🧑‍🔧 Human-reviewed fixes


<div align="center">

<br />

**Built step by step, safely first. 🔧**

</div>
