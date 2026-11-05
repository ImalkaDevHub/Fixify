<div align="center">

# 🔧 Fixify

### Find bugs. Understand them. Fix them. Keep humans in control.

Fixify scans websites in a real browser, explains what broke with AI, and proposes code fixes that become GitHub pull requests only after a person approves them.

![Next.js](https://img.shields.io/badge/Next.js-16-000000?style=flat-square&logo=nextdotjs&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-async-009688?style=flat-square&logo=fastapi&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-Alembic-4169E1?style=flat-square&logo=postgresql&logoColor=white)
![Playwright](https://img.shields.io/badge/Playwright-Chromium-2EAD33?style=flat-square&logo=playwright&logoColor=white)

</div>

> [!IMPORTANT]
> Current status: **complete with limitations**. See [docs/status.md](docs/status.md) for what has been verified, what needs external credentials, and the remaining production blockers. Only scan websites you are authorized to test.

## What it does

| Step | What happens |
|---|---|
| 🔐 **Accounts** | Registration, email verification, login, password reset, sessions, account deletion. Every project belongs to one user. |
| 🕷️ **Scan** | A separate worker opens the site in headless Chromium and runs rule-based checks: navigation, console errors, exceptions, failed requests, HTTP errors, broken links, images, alt text, headings, meta description, mixed content, load time, and a screenshot. |
| 🧠 **Analyze** | AI (Claude by default) explains a finding from its recorded, sanitized evidence: summary, root cause, impact, solution, complexity, confidence, related code. |
| 🐙 **Connect GitHub** | OAuth, repository and branch selection. Files are read through the API, never cloned or executed. |
| 🛠️ **Propose a fix** | AI proposes search-and-replace edits against real files; Fixify validates them before anyone sees them. |
| 👀 **Review** | Side-by-side diff, approve, reject, comment, regenerate with feedback, reopen. |
| 🔀 **Pull request** | Approved fixes are committed to a new `fixify/…` branch and opened as a pull request. Fixify never merges. |
| 📊 **Track** | Dashboard, analytics from persisted data, in-app notifications, scheduled scans. |

## Architecture

```mermaid
flowchart LR
    U([Browser]) --> W["Next.js web app<br/>apps/web :3000"]
    W -->|"/api/v1/* rewrite (same origin)"| A["FastAPI<br/>services/api :8000"]
    A --> P[("PostgreSQL")]
    A -->|run IDs| R[("Redis (optional)")]
    K["Worker<br/>scans · jobs · scheduler"] <--> P
    R --> K
    K -->|stripped env| S["Scanner process"] --> X["Egress proxy<br/>URL policy"] --> C["Headless Chromium"]
    K -->|AI jobs| AI["Claude API"]
    K -->|"GitHub REST (user token)"| G["GitHub"]
```

Details: [docs/architecture.md](docs/architecture.md) · [docs/security.md](docs/security.md) · [docs/scanner.md](docs/scanner.md)

## Quick start (Windows PowerShell)

Prerequisites: Python 3.12+, Node.js 20.9+, PostgreSQL (Docker Desktop, a native install, or a hosted database), and optionally Redis.

```powershell
# 1. Configuration
Copy-Item .env.example .env          # then edit DATABASE_URL (and optional AI / GitHub keys)
# Without Redis, set QUEUE_BACKEND=database and REDIS_REQUIRED=false in .env

# 2. Infrastructure (skip if you use native or hosted PostgreSQL)
docker compose --env-file .env -f infra/docker-compose.yml up -d

# 3. Backend
cd services/api
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m playwright install chromium
alembic upgrade head
python -m app.serve                  # API on http://127.0.0.1:8000
```

Second terminal (worker: scans, AI and GitHub jobs, scheduler):

```powershell
cd services/api
.\.venv\Scripts\Activate.ps1
python -m app.worker
```

Third terminal (web app):

```powershell
cd apps/web
Copy-Item .env.example .env.local
npm install
npm run dev                          # http://localhost:3000
```

Open <http://localhost:3000>, create an account, and verify the email. With `EMAIL_BACKEND=console` the verification link is printed in the API terminal. Then add a project and run a scan.

> Projects created before authentication existed have no owner and are hidden. Assign them to your account with `python -m app.cli assign-orphans --email you@example.com`.

## Configuration

| Area | Required for | Settings | Guide |
|---|---|---|---|
| Database | everything | `DATABASE_URL` | [development-setup](docs/development-setup.md) |
| Sessions | production | `SECRET_KEY`, `PUBLIC_APP_URL` | [authentication](docs/authentication.md) |
| Email | verification and reset links | `EMAIL_BACKEND=smtp`, `SMTP_*` | [authentication](docs/authentication.md) |
| AI | analysis and fixes | `ANTHROPIC_API_KEY`, `AI_MODEL`, `AI_EFFORT` | [ai](docs/ai.md) |
| GitHub | repositories and pull requests | `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET`, `TOKEN_ENCRYPTION_KEY` | [github-oauth](docs/github-oauth.md) |

Every setting, with its default and bounds, is in [services/api/.env.example](services/api/.env.example). Never put secrets in `NEXT_PUBLIC_*` variables; the web app needs only the server-side `API_INTERNAL_URL`.

## Checks

```powershell
cd services/api; .\.venv\Scripts\Activate.ps1; pytest; ruff check .; alembic check
cd apps/web; npm run lint; npm run typecheck; npm test; npm run build
```

See [docs/testing.md](docs/testing.md) for what each suite covers, and [docs/deployment.md](docs/deployment.md) before deploying anywhere shared.

## Documentation

[Architecture](docs/architecture.md) · [Scanner](docs/scanner.md) · [Security](docs/security.md) · [Authentication](docs/authentication.md) · [AI](docs/ai.md) · [GitHub OAuth](docs/github-oauth.md) · [API](docs/api.md) · [Development setup](docs/development-setup.md) · [Testing](docs/testing.md) · [Deployment](docs/deployment.md) · [Status and limitations](docs/status.md)
