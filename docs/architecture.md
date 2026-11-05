# Fixify architecture

## Processes

| Process | Command | Role |
|---|---|---|
| Web app | `npm run dev` / `next start` (apps/web) | Next.js 16 App Router UI. Rewrites `/api/v1/*` to FastAPI so the browser stays on one origin. `proxy.ts` redirects signed-out visitors; real authorization is always done by the API. |
| API | `python -m app.serve` (services/api) | FastAPI. Validates requests, enforces ownership, queues work, returns results. Never runs a browser, an AI call, or a GitHub write in a request handler. |
| Worker | `python -m app.worker` | Runs three loops: the **scan worker**, the **job worker** (AI analysis, fix generation, pull requests), and the **scheduler**. |
| Scanner | started by the worker per scan | Isolated subprocess with a stripped environment (no DB/Redis credentials), egress proxy, headless Chromium. |

PostgreSQL is the source of truth for every run and job. Redis (optional) only announces scan IDs promptly.

## Backend layering

`Router → Pydantic schema → Service → Repository → SQLAlchemy model`. Routers translate HTTP to service calls and service errors back to HTTP. Every user-facing repository query takes an `owner_id`; unscoped lookups exist only for the worker (`get_project_unscoped`, `get_run`).

| Module | Purpose |
|---|---|
| `app/api/deps.py` | Session cookie authentication, CSRF and Origin checks, verified-email gate, rate limits |
| `app/services/auth.py` | Registration, login, rotating refresh tokens, email tokens, password changes, account deletion |
| `app/services/project.py`, `scan.py` | Projects and scans (ownership, limits, comparison) |
| `app/services/analysis.py` | AI finding analysis (worker handler) |
| `app/services/github.py`, `repository_files.py` | OAuth, encrypted tokens, repository selection, allow-listed file access |
| `app/services/fixes.py`, `fix_validation.py` | Fix generation, validation, review state machine, pull requests |
| `app/services/jobs.py`, `app/worker/jobs.py` | Background job queue and worker |
| `app/services/notifications.py`, `scan_events.py` | In-app notifications and preferences |
| `app/services/schedules.py`, `app/worker/scheduler.py` | Scheduled scans |
| `app/services/analytics.py` | Charts data from persisted scans |
| `app/ai/provider.py`, `prompts.py` | Provider abstraction (Anthropic SDK), prompts, schemas, untrusted-content boundary |
| `app/integrations/github.py` | Minimal GitHub REST client |

## Data model

```text
users 1─* user_sessions, user_tokens, 1─1 github_connections, user_preferences, *─ notifications
users 1─* projects 1─* test_runs 1─* test_case_results, findings, scan_artifacts
projects 1─1 scan_schedules
findings 1─* ai_analyses
findings 1─* fix_proposals 1─* fix_reviews, 1─1 pull_requests
projects 1─* background_jobs (subject = finding or fix)
```

Migrations: `0001_projects`, `0002_scans`, `0003_auth` (users, sessions, tokens, `projects.owner_id`), and `0004_platform` (jobs, analyses, GitHub connections, fixes, reviews, pull requests, notifications, preferences, schedules, project scan settings, `test_runs.trigger`). `0005_site_verification` adds the project ownership-verification fields. All primary keys are UUIDs. Deleting a user cascades to everything they own. Screenshots stay on disk under `ARTIFACT_DIR`; fixes store bounded snippets plus the Git blob SHA, never whole files.

## Main flows

**Scan.** `POST /projects/{id}/scans` (verified owner, URL policy, per-user and global limits) → `test_runs` row `queued` → the worker claims it atomically → scanner subprocess → results and terminal status in one transaction → notifications.

**Analysis.** `POST /findings/{id}/analysis` → `background_jobs` (`analyze_finding`, idempotent while active) → the job worker builds a prompt from sanitized evidence (plus allow-listed repository paths when connected) → schema-checked JSON → model-supplied paths and IDs are filtered to known values → `ai_analyses` row and job success in one transaction.

**Fix.** `POST /findings/{id}/fixes` → `generate_fix` job → repository snapshot (branch head and tree) → up to `GITHUB_MAX_FILES_PER_FIX` allow-listed files → model returns edits → each edit must match its file exactly once → syntax checks → `fix_proposals` (`pending_review` or `failed_validation`).

**Review and pull request.** Approve, reject, reopen, or comment (`fix_reviews`) → `POST /fixes/{id}/pull-request` (approved only) → `create_pull_request` job → edits are re-applied against the *current* branch head (a conflict fails safely) → blobs, tree, commit, new `fixify/fix-…` branch, pull request → fix `applied`. Retries reuse an existing branch or pull request.

**Schedules.** The scheduler claims due schedules with a conditional update on `next_run_at`, so concurrent workers cannot start a scheduled scan twice, then creates the scan with `trigger="scheduled"`.

## Reliability

| Mechanism | Scans | Jobs |
|---|---|---|
| Atomic claim (`queued → running`, attempt + 1) | ✓ | ✓ |
| Heartbeat while running | 15 s | 15 s |
| Stale recovery | 90 s | 180 s |
| Bounded retries | `SCAN_MAX_ATTEMPTS` | `JOB_MAX_ATTEMPTS`, exponential backoff, transient errors only |
| Result and status in one transaction, owner attempt only | ✓ | ✓ |
| Visible failure reason | `failure_reason` | `error` and a `job_failed` notification |

All of these are at-least-once execution with idempotent storage, not exactly-once execution.
