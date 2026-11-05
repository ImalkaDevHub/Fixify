# Testing

## Backend (`services/api`)

```powershell
.\.venv\Scripts\Activate.ps1
pytest            # 311 tests, 2 skipped (opt-in: PostgreSQL migration test, browser E2E)
ruff check .
alembic check     # models vs. migrations, against DATABASE_URL (read-only)
```

Tests use an in-memory SQLite database, fake DNS, a fake queue, a recording email sender, a scripted AI provider, and an in-memory GitHub (`tests/platform_fakes.py`). They never read your `.env` (`FIXIFY_IGNORE_ENV_FILE`) and never reach the internet. Scanner engine tests drive real headless Chromium against a local fixture site, and are skipped if Chromium is not installed.

| Suite | Covers |
|---|---|
| `test_auth.py` | Registration, cookies, verification, login, rate limits, CSRF, Origin, tampered and expired tokens, refresh rotation and reuse, logout, password reset and change, sessions, account deletion, production settings guard |
| `test_ownership.py` | Projects, scans, findings, artifacts, comparison, cancel, and dashboard isolated between users; a sweep over every project-scoped endpoint (verification, schedule, repository, tree, analytics) as another user; per-user limits; orphan projects |
| `test_ai_github_fixes.py` | AI unavailable state, analysis job, output filtering, prompt-injection boundary, secret redaction, retries and failures, OAuth state binding, encrypted tokens, revoked tokens, allow-listed files, fix generation, validation failures, path escapes, approval workflow, pull request, conflict safety, regenerate, isolation |
| `test_platform_units.py` | Notifications and preferences, schedule maths and duplicate prevention, analytics new/resolved, cross-project lists, fix validation and syntax checks (full JavaScript / JSX / TypeScript / TSX / CSS parsers via tree-sitter), path rules, redaction, Fernet rotation, Anthropic request shape and error mapping |
| `test_worker.py` | Atomic claims, duplicate delivery, retries, stale-run recovery, idempotent results, artifact safety, surviving a database outage (scan and job loops), SIGTERM reaching the clean-shutdown path |
| `test_content_checks.py` | New content, accessibility, and performance checks (unit and real browser) |
| `test_site_verification.py` | Ownership verification through the real egress proxy: meta tag, `/.well-known` file, wrong token, cross-host redirects, host change, isolation, internal addresses |
| `tests/e2e/test_workflow.py` | **Browser E2E (opt-in):** register → verify → project → scan → finding → AI analysis → GitHub connect → repository → fix → diff → approve → pull request |
| existing suites | Projects, scans API, worker lifecycle, URL policy, scanner rules and engine |

**Migration test against real PostgreSQL.** It upgrades, checks for drift, then downgrades to an empty schema, so it refuses any database whose name lacks `test`. With the local Compose PostgreSQL (from the repository root, then `services/api`):

```powershell
docker compose --env-file .env -f infra/docker-compose.yml exec postgres createdb -U fixify_user fixify_migration_test
cd services/api
$env:TEST_DATABASE_URL = "postgresql+psycopg://fixify_user:PASSWORD@127.0.0.1:5433/fixify_migration_test"
pytest tests/test_migrations.py
```

## Frontend (`apps/web`)

```powershell
npm run lint
npm run typecheck
npm test          # node:test unit tests (diff engine, link safety, formatters, CSP)
npm run build
```

## Browser end to end (mock AI, fake GitHub)

`tests/e2e/stack.py` is a **test harness only**. It runs the real API, scan worker, and job worker against:

- a throwaway SQLite database, **or**, with `--database-url` and `--redis-url`, a disposable local PostgreSQL database named `*test*` (schema built by the real Alembic migrations) and the real Redis queue;
- a clearly labelled mock AI provider (`mock-e2e`);
- the in-memory fake GitHub API and a fake authorization page;
- the scanner's fixture website.

It needs no keys and never touches your real database.

```powershell
# terminal 1 (stop the normal API first: the harness uses port 8000)
cd services/api; .\.venv\Scripts\Activate.ps1
python -m tests.e2e.stack --data $env:TEMP\fixify-e2e
# terminal 2
cd apps/web; npm run dev
# terminal 3
cd services/api; .\.venv\Scripts\Activate.ps1
$env:E2E_DATA_DIR = "$env:TEMP\fixify-e2e"; pytest tests/e2e/test_workflow.py
```

You can also open http://localhost:3000 while the harness runs and click through the same flow by hand. The harness prints the fixture URL to scan.

PostgreSQL + Redis variant of terminal 1 (create `fixify_e2e_test` first, like the migration test database):

```powershell
python -m tests.e2e.stack --data $env:TEMP\fixify-e2e `
    --database-url "postgresql+psycopg://fixify_user:PASSWORD@127.0.0.1:5433/fixify_e2e_test" `
    --redis-url "redis://127.0.0.1:6379/15"
```

## Launcher (`scripts/launcher`)

```powershell
services\api\.venv\Scripts\python.exe -m unittest discover -s scripts/launcher/tests -v
```

These use real supervised processes and cover: start, duplicate detection, graceful and forced stop, startup crash, stale and reused PIDs, port conflicts, missing Docker, missing `.env`, the menu, and secrets never being printed.

## Manual checks against a real database

These were verified manually in a real browser against the development database: register, verify email, sign in, create project, run scan, live status, report, screenshot, finding, notifications, analytics, mobile layout, sign out, and protected-route redirect. The AI, GitHub, fix, and pull-request steps were verified in the browser with the harness above (mock AI, fake GitHub). They still need one run with real Claude and GitHub credentials (see [status.md](status.md)).

## GitHub Actions CI

The CI workflow runs the frontend checks, backend and launcher suites, PostgreSQL migration validation, Chromium scanner tests, PostgreSQL + Redis browser workflow, Docker image builds, and security checks as independent jobs. The final **CI result** job is the required aggregate status. `main` and `development` pushes and pull requests trigger it; `workflow_dispatch` allows a manual run.

The PostgreSQL migration job starts with an empty, disposable `fixify_migration_test` database, applies migrations, checks model drift, downgrades to base through the existing migration test, reapplies to head, and verifies that the database has exactly the single latest revision. The integration job uses disposable PostgreSQL and Redis service containers. It drives the existing E2E harness against its local fixture site through the API, Redis-backed worker, and web app. AI and GitHub are mocked as described above; this does not verify real external credentials.

The scanner job installs Chromium and its Linux dependencies, then runs `tests/test_scanner_engine.py`; scanner targets are local fixtures only. Docker builds all three application images without pushing them, verifies non-root users and absence of `.env` files, and checks that Chromium is present in the worker image. Security checks include `npm audit`, `pip-audit`, `pip check`, Gitleaks over git history, `actionlint`, and zizmor.

Equivalent local checks:

```bash
# Frontend
cd apps/web
npm ci
npm run lint
npm run typecheck
npm test
API_INTERNAL_URL=http://127.0.0.1:8000 npm run build
npm audit --audit-level=high

# Backend and browser scanner (from the repository root)
python -m pip install -e "services/api[dev]"
cd services/api
ruff check .
ruff format --check .
pytest --ignore=tests/test_scanner_engine.py --ignore=tests/e2e -q
python -m playwright install --with-deps chromium
pytest tests/test_scanner_engine.py -q
```

The PostgreSQL migration test and browser E2E harness are opt-in locally; use only disposable databases whose names include `test` as documented above. CI creates isolated service containers and never connects to developer or production infrastructure. GitHub Actions has not been run remotely yet; inspect the **Actions** tab after the first push or pull request for actual hosted-runner results.
