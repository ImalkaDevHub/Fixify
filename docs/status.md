# Fixify status

**Overall: LOCAL DEVELOPMENT READY. Not production ready.** The architecture matches the intended design. Every workflow step is implemented and covered by automated tests. The open items are listed under [Remaining work](#remaining-work).

Audit and verification: 2026-11-05.

## Architecture

| Layer | Intended | Actual | Status |
|---|---|---|---|
| Frontend | Next.js App Router + TypeScript | Next.js 16.4 App Router, TypeScript, same-origin `/api/v1/*` rewrite | ✔ |
| API | FastAPI | FastAPI; enqueues scans and never runs a browser (Playwright is imported only by the scanner) | ✔ |
| Database | Self-managed PostgreSQL | PostgreSQL 17 (Docker Compose) or native; SQLAlchemy 2 (async, psycopg 3); Alembic `0001`→`0005` | ✔ |
| Queue | Redis | Redis 7 (default `QUEUE_BACKEND=redis`); PostgreSQL stays the source of truth (atomic claims, database sweep) | ✔ |
| Worker | Separate Python worker | `python -m app.worker`: scans in an isolated scanner subprocess (Playwright + Chromium, egress proxy), AI and GitHub jobs, scheduler | ✔ |
| AI | Anthropic Claude | Official `anthropic` SDK, structured JSON output | ✔ (mock-verified) |
| GitHub | OAuth + REST API | OAuth App, Git Data API, pull requests | ✔ (fake-verified) |
| Local infra | Docker Compose: PostgreSQL + Redis | `infra/docker-compose.yml`: health checks, persistent volumes, `127.0.0.1` binding, configurable host ports | ✔ |
| Supabase | Not a dependency | **No Supabase code, client, Auth or Storage.** The only dependency was a development `DATABASE_URL`; it now points at the local database | ✔ removed |

## Feature checklist

Status: **CV** complete and verified (automated tests, plus a real run where noted) · **IV** implemented, verified only with mocks or fakes · **P** partial · **M** missing · **B** broken (fixed in this audit unless noted).

| Area | Feature | Status | Evidence |
|---|---|---|---|
| Auth | Registration, email verification, login/logout, Argon2id hashing | CV | `test_auth.py` |
| Auth | Access JWT + DB-checked session, rotating refresh with reuse detection, CSRF + Origin, expiry | CV | `test_auth.py` |
| Auth | Password reset/change, sessions list/revoke, account deletion | CV | `test_auth.py` |
| Auth | Login throttling (per IP and per account, Redis-shared) | CV | `test_auth.py` |
| Auth | 2FA | M | documented gap |
| Isolation | Projects, scans, findings, artifacts, comparison, notifications, analytics, schedules, repository, verification, fixes, jobs, sessions | CV | `test_ownership.py` (new sweep over every project-scoped endpoint), `test_ai_github_fixes.py`, `test_platform_units.py` |
| Projects | Create, list, search, detail, update, delete, limits | CV | `test_projects.py`, `test_ownership.py` |
| Scans | Start (enqueue), history, detail, compare, cancel, duplicate prevention, capacity limits | CV | `test_scans_api.py` |
| Scanner | Navigation/status, redirects, timeouts, console errors, exceptions, failed requests, 4xx/5xx, links (confirmed vs. "may be broken"), title, H1, viewport, favicon, images, alt text, meta description, mixed content, slow load, screenshot | CV | `test_scanner_engine.py` (real Chromium, local fixture site), `test_scanner_rules.py`, `test_content_checks.py` |
| Scanner | SSRF: URL policy, DNS pinning, egress proxy, private-network block | CV | `test_url_policy.py`, `test_site_verification.py` |
| Worker | Atomic claim, heartbeats, retries, stale recovery, idempotent persistence, artifact cleanup safety | CV | `test_worker.py` |
| Worker | Survives a database outage (scan and job loops) | **B → fixed** | a DB error escaped `run_forever` and stopped the whole process; now logged and retried with backoff (`test_worker.py`) |
| Worker | Graceful shutdown on SIGTERM / Ctrl+Break | **P → fixed** | only SIGINT reached `shutdown()`; now all three do, so in-flight scans are re-queued at once (`test_worker.py`) |
| Scheduler | Daily / weekly / every N h (≥ 6), UTC, duplicate-safe claiming | CV | `test_platform_units.py` |
| AI | Analysis, structured output, redaction, untrusted-content boundary, retries/timeouts, per-user hourly limit, `max_tokens` | IV | mock provider; real Claude not run |
| AI | Dependency declared | **B → fixed** | `anthropic` was imported but missing from `pyproject.toml`; a fresh install or image would crash the worker |
| Fixes | Generation, exact-match edits, review, approve/reject, regenerate, reopen | IV | `test_ai_github_fixes.py` |
| Fixes | JavaScript / TypeScript / CSS validation | **P → fixed** | bracket balance only; now real tree-sitter parsers (JS/JSX, TS, TSX, CSS), comparative, parse-only |
| GitHub | OAuth with bound state, Fernet-encrypted tokens, revocation, repository/branch checks, push-permission check, PR creation, never merges | IV | fake GitHub; real GitHub not run |
| Notifications | All event types, unread count, read/read-all, preferences | CV | `test_platform_units.py` |
| Analytics | Totals, severity, new vs. resolved, duration, health, per-day series; no N+1 | CV | `test_platform_units.py` |
| Web | All pages, auth redirects, loading/empty/error states, no placeholder features | CV | build; browser checks |
| Web | Content Security Policy | **P → fixed** | `'unsafe-inline'` scripts; now nonce + `'strict-dynamic'` (verified in a browser: all 19 scripts carry the nonce, no violations, hydration works) |
| Web | App icon | **M → fixed** | `app/icon.svg` (Fixify's own scanner flagged its absence) |
| Launcher | start/stop/restart/status/logs/migrate/infra/open/help, PID safety, rollback, Ctrl+C | CV | 24 launcher tests; real runs |
| Launcher | Configurable Compose host ports | **M → fixed** | `POSTGRES_HOST_PORT` / `REDIS_HOST_PORT` |
| Docker | Migrations in the container stack | **M → fixed** | one-shot `migrate` service; API and worker wait for it |
| Docker | Image health checks | **M → fixed** | API (`/health`) and web |

## Test results

All run on 2026-11-05 on Windows 11 (Python 3.14.7, Node.js 24.20.0, Docker 29.8.0).

| Check | Command | Result |
|---|---|---|
| Backend tests | `pytest` (services/api) | **311 passed**, 2 skipped (the opt-ins below, run separately) |
| Backend lint | `ruff check .` | passed |
| Launcher tests | `python -m unittest discover -s scripts/launcher/tests` | **24 passed** |
| Frontend | `npm run lint`, `npm run typecheck`, `npm test`, `npm run build` | passed; **11** tests; every route rendered per request (nonce CSP) |
| Infrastructure | `.\fixify.ps1 infra` | PostgreSQL 17.11 (`127.0.0.1:5433`) and Redis 7.4.12 (`127.0.0.1:6379`) containers healthy; persistent volumes |
| Migrations on a clean database | `.\fixify.ps1 migrate --yes` | `0001` → `0005` applied to the empty `fixify` database |
| Model drift | `alembic check` | no new operations |
| Migration round trip | `TEST_DATABASE_URL=… pytest tests/test_migrations.py` | **passed** (upgrade, drift check, downgrade to empty) on `fixify_migration_test` |
| Browser E2E, PostgreSQL + Redis | `tests.e2e.stack --database-url …/fixify_e2e_test --redis-url …` + `pytest tests/e2e/test_workflow.py` | **passed** (29 s): register → verify → project → scan of the local fixture site through the Redis queue → 5 findings + screenshot stored in PostgreSQL → AI analysis (mock) → GitHub connect (fake) → fix → review → approve → pull request |
| Browser E2E, SQLite + Redis | same, without `--database-url` | passed (30 s) |
| CSP in a browser | production build, `/login` | all 19 scripts carry the nonce, no console violations, React hydrated (client-side validation works) |
| Launcher start on the real stack | `.\fixify.ps1 start` | API ready (`/health/ready`: database and Redis), worker started; web step refused because a manually started `next dev` held port 3000, and the run rolled back cleanly. **A complete start including the web app is not verified on this machine** |
| Worker shutdown (Windows) | `.\fixify.ps1 stop` | `Received SIGBREAK; shutting down` → `Worker stopped`, exit code 0 (was killed with `0xC000013A` before the fix) |
| API image | `docker build services/api` | **built** (589 MB) and run on the Compose network: Docker health check `healthy`, `/health/ready` ready (PostgreSQL + Redis), runs as `fixify` (non-root), no `.env` in the image, `alembic upgrade head` works with `--read-only` (the `migrate` service) |
| Web image | `docker build apps/web` | **not built**: `npm ci` fails inside the build (see below) |
| Worker image | `docker build -f Dockerfile.worker` | **not attempted**: about 2 GB Playwright base image over this network |

**Why the web image did not build here.** This network's firewall (Fortinet) re-signs TLS for `registry.npmjs.org`. Inside containers that certificate is untrusted, so `npm ci` fails (`unable to verify the first certificate`, reproduced twice; `npm view` in a plain `node:22-alpine` container fails the same way). PyPI is not intercepted, which is why the API image built. TLS verification was not disabled. Image downloads from Docker Hub were very slow, and stalled several times.

## Remaining work

1. **Real-credential runs:** Claude (`ANTHROPIC_API_KEY`) and a GitHub OAuth app. These flows are verified only with the mock provider and the fake GitHub API.
2. **Production blockers** (details in [security.md](security.md#known-gaps)): network-isolated scanner without database credentials; DNS TXT site verification; 2FA (recommended); a GitHub App instead of the OAuth `repo` scope (recommended).
3. **Web and worker images** still need to be built and run on a network without TLS inspection. A CI runner will do this in the next phase.
4. **One complete `.\fixify.ps1 start` including the web app** on this machine: run it once while no manual `next dev` holds port 3000. The web step itself is covered by the launcher tests, and earlier runs started the API and worker.
5. **Production email (SMTP)** is configured but untested; development uses the console backend.

## Database changes

None in this audit. `0003_auth`, `0004_platform` and `0005_site_verification` are additive. Data from the earlier hosted development database was exported read-only (`backups/`, git-ignored) and was **not** imported automatically; see [development-setup.md](development-setup.md#importing-data-from-an-earlier-database).
