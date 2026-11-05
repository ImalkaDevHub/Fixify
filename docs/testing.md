# Testing

## Backend (`services/api`)

```powershell
.\.venv\Scripts\Activate.ps1
pytest            # 298 tests, 2 skipped (opt-in: PostgreSQL migration test, browser E2E)
ruff check .
alembic check     # models vs. migrations, against DATABASE_URL (read-only)
```

Tests use an in-memory SQLite database, fake DNS, a fake queue, a recording email sender, a scripted AI provider, and an in-memory GitHub (`tests/platform_fakes.py`). They never read your `.env` (`FIXIFY_IGNORE_ENV_FILE`) and never reach the internet. Scanner engine tests drive real headless Chromium against a local fixture site, and are skipped if Chromium is not installed.

| Suite | Covers |
|---|---|
| `test_auth.py` | Registration, cookies, verification, login, rate limits, CSRF, Origin, tampered and expired tokens, refresh rotation and reuse, logout, password reset and change, sessions, account deletion, production settings guard |
| `test_ownership.py` | Projects, scans, findings, artifacts, comparison, cancel, and dashboard isolated between users; per-user limits; orphan projects |
| `test_ai_github_fixes.py` | AI unavailable state, analysis job, output filtering, prompt-injection boundary, secret redaction, retries and failures, OAuth state binding, encrypted tokens, revoked tokens, allow-listed files, fix generation, validation failures, path escapes, approval workflow, pull request, conflict safety, regenerate, isolation |
| `test_platform_units.py` | Notifications and preferences, schedule maths and duplicate prevention, analytics new/resolved, cross-project lists, fix validation and syntax checks, path rules, redaction, Fernet rotation, Anthropic request shape and error mapping |
| `test_content_checks.py` | New content, accessibility, and performance checks (unit and real browser) |
| `test_site_verification.py` | Ownership verification through the real egress proxy: meta tag, `/.well-known` file, wrong token, cross-host redirects, host change, isolation, internal addresses |
| `tests/e2e/test_workflow.py` | **Browser E2E (opt-in):** register → verify → project → scan → finding → AI analysis → GitHub connect → repository → fix → diff → approve → pull request |
| existing suites | Projects, scans API, worker lifecycle, URL policy, scanner rules and engine |

**Migration test against real PostgreSQL** (it downgrades to an empty schema, so use a throwaway database):

```powershell
$env:TEST_DATABASE_URL = "postgresql+psycopg://USER:PASSWORD@HOST:5432/fixify_migration_test"
pytest tests/test_migrations.py
```

## Frontend (`apps/web`)

```powershell
npm run lint
npm run typecheck
npm test          # node:test unit tests (diff engine, link safety, formatters)
npm run build
```

## Browser end to end (mock AI, fake GitHub)

`tests/e2e/stack.py` is a **test harness only**. It runs the real API, scan worker, and job worker against:

- a throwaway SQLite database;
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

## Manual checks against a real database

These were verified manually in a real browser against the development database: register, verify email, sign in, create project, run scan, live status, report, screenshot, finding, notifications, analytics, mobile layout, sign out, and protected-route redirect. The AI, GitHub, fix, and pull-request steps were verified in the browser with the harness above (mock AI, fake GitHub). They still need one run with real Claude and GitHub credentials (see [status.md](status.md)).
