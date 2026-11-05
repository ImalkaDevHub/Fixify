# Fixify status

**Overall: COMPLETE WITH LIMITATIONS.** Every workflow step, from registration through to the pull request, was verified in a real browser. The scan path ran against the real Supabase database. The AI and GitHub steps ran against a mock AI provider and a fake GitHub API, because no real credentials were available. The remaining limitations are listed below.

Verified on 2026-11-05.

## Verification

| Check | Result |
|---|---|
| Backend `pytest` | **298 passed**, 2 skipped (opt-in: destructive migration test, browser E2E) |
| `ruff check .` | passed |
| `alembic upgrade head` on PostgreSQL 17 (Supabase dev database) | 0001 → 0005 applied |
| `alembic check` (models vs migrations, PostgreSQL) | no drift |
| Frontend `eslint`, `tsc --noEmit`, `npm test` (8), `next build` | all passed |
| Real browser, against the Supabase database | Register (including a server validation error), console email link, verify email, dashboard onboarding, create project, run a real scan of example.com (9/9 checks, 2 accurate info findings, 6.5 s), live status, report, authenticated screenshot, finding page, honest "AI not configured" and "GitHub not configured" states, notification, analytics, mobile 375 px (no horizontal overflow on any main page), sign out, protected-route redirect |
| AI analysis, GitHub OAuth, fix generation, review, approval, branch, commit, pull request | **Verified in a real browser with the E2E harness** (`tests/e2e/stack.py`: mock AI, fake GitHub, throwaway SQLite), both by hand and with the automated Playwright test `tests/e2e/test_workflow.py` (passed twice, about 19 s). Also covered by backend tests. **Not yet run against real Claude or GitHub.** |
| Docker images (`api`, `web`, `worker`) | **Not built**: the Docker daemon was not running |

## Implemented

**Authentication.** Argon2id; JWT access cookie with a per-request session check; rotating refresh token with reuse detection; session-bound CSRF and Origin checks; email verification; password reset and change; session management; account deletion; rate limits; production settings guard.

**Ownership.** `projects.owner_id`, with every query scoped by owner. Other users' objects return 404. Pre-auth projects are kept hidden, and `app.cli assign-orphans` assigns them.

**Projects.** Create, edit, delete, search; description; links per scan; repository and branch; schedule; latest scan; history.

**Scanner.** All existing checks, plus content, accessibility, and performance indicators: broken images, alt text, multiple `<h1>`, meta description, active and passive mixed content, slow load (suspected).

**AI analysis.** Provider abstraction on the official Anthropic SDK with structured JSON output, effort, refusal fallback, timeouts, and retries. Untrusted-content boundary, secret redaction, output filtering. Honest unavailable state.

**GitHub.** OAuth with bound state, Fernet-encrypted tokens, repository and branch selection checked with GitHub, revoked-token detection, disconnect with grant revocation, allow-listed file access.

**Fixes.** Generation from real files; exact-match edit validation; syntax checks; statuses (pending review, approved, rejected, applied, failed validation, superseded); history; regenerate with feedback; reopen; reviews and comments.

**Pull requests.** Approval required; edits re-applied against the current branch head; new `fixify/…` branch; idempotent retries; status refresh; never merged.

**Background jobs.** The worker runs scans, AI and GitHub jobs, and the scheduler, with claims, heartbeats, retries with backoff, stale recovery, and visible errors.

**Notifications.** Scan started (off by default), completed, failed, critical findings, analysis complete, fix ready, validation failed, pull request created, job failed. Unread count, mark read, mark all, preferences.

**Schedules.** Daily, weekly, or every N hours (minimum 6). Duplicate-safe claiming; respects verification and limits; records the outcome.

**Analytics.** Totals, severity, new versus resolved, duration, health score, and per-day series, from persisted data only, with empty states.

**UI.** Dark design system with the requested palette (Inter and JetBrains Mono); landing page; collapsible sidebar and mobile drawer; breadcrumbs; notification bell; every page listed in the request; Recharts charts; side-by-side and unified syntax-highlighted diff review; Motion animations respecting `prefers-reduced-motion`; skeletons and empty states.

## Added in the final pass

- **Website ownership verification:** a meta tag or `/.well-known` file, checked through the egress proxy, bound to the hostname, and required by default in production. Migration `0005`.
- **Safer screenshot cleanup:** the artifact directory records its database, so a worker pointed at another database no longer deletes that environment's screenshots.
- **Analytics without N+1 queries:** baselines come from two queries in total, whatever the number of projects.
- **Timestamps without a zone are read as UTC** in the UI.
- **Mock-AI / fake-GitHub E2E harness**, plus an automated browser workflow test.

## Needs external credentials

| Feature | Settings |
|---|---|
| AI analysis and fix generation | `ANTHROPIC_API_KEY` (optionally `AI_MODEL`, `AI_EFFORT`) |
| GitHub connection, repositories, pull requests | `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET`, `TOKEN_ENCRYPTION_KEY` (OAuth app callback `…/github/callback`) |
| Real verification and reset emails | `EMAIL_BACKEND=smtp`, `SMTP_*` |

## Database changes

- `0003_auth`: `users`, `user_sessions`, `user_tokens`, and `projects.owner_id`.
- `0004_platform`: `background_jobs`, `ai_analyses`, `github_connections`, `fix_proposals`, `fix_reviews`, `pull_requests`, `notifications`, `user_preferences`, `scan_schedules`, `projects.description`, `projects.scan_max_links`, and `test_runs.trigger`.

Both are additive; no existing table or row is removed. See [api.md](api.md) for every new endpoint.

## Known limitations and production blockers

1. **Real-credential run still to do.** The AI, OAuth, fix, and pull-request flows work against the mock and fake, but have not been run against Claude and GitHub.
2. **Browser isolation is in-process** (egress proxy and launch flags), and the worker holds database credentials. Production needs a network-isolated scanner (see [security.md](security.md)).
3. **Ownership verification proves control of one page, not authorization.** No DNS TXT method, and it is optional outside production.
4. **Rate limits are per process without Redis.**
5. **The CSP allows inline scripts.** Nonce-based CSP not implemented.
6. **The OAuth App `repo` scope is broad.** A GitHub App would be more granular.
7. **No 2FA or account lockout.**
8. **Syntax validation is basic for JS, TS, and CSS** (bracket balance, not a full parser). Fixes are never executed or tested by Fixify; repository CI must run on the pull request.
9. **Docker images not built or verified** in this environment.
10. **Fixed: switching the worker's database no longer deletes screenshots.** Before the fix, the first worker start against the new Supabase database removed 2 old screenshot folders from earlier local scans. Those cannot be recovered.
11. **Remote database latency.** Each page load makes several round trips, which is noticeable over a hosted database far from the API.
