# Fixify platform implementation plan

This plan is based on an audit of the repository at commit `c94b95a` ("step 2 is done").

## Phase 0: audit findings (verified, not assumed)

| Area | What exists | Gap |
|---|---|---|
| Backend layering | FastAPI routers → Pydantic schemas → services → repositories → SQLAlchemy 2 async models | Some routes call repositories directly (`cancel_scan`, `delete_project`) |
| Data | `projects`, `test_runs`, `test_case_results`, `findings`, `scan_artifacts`; Alembic `0001`, `0002` | No users, no ownership; `repo_full_name` / `github_repo_id` / `default_branch` columns exist but are unused |
| Scanner | Isolated subprocess, egress proxy, 8 checks, fingerprints, redaction, scan comparison | Additional checks requested (images, alt text, meta description, mixed content, slow load) |
| Worker | Atomic claim, heartbeats, retries, stale recovery, idempotent persistence | Scan-only: no generic background-job system for AI and GitHub work, no scheduler |
| API security | URL policy, artifact path validation, generic DB errors | **No authentication**: every project, scan, finding and screenshot is public; CORS has `allow_credentials=False` |
| Frontend | Next.js 16.4 App Router, typed fetch client, polling hook, light-theme CSS | Talks to the API cross-origin through `NEXT_PUBLIC_API_BASE_URL`; no auth, charts, animation or design system |
| Tests | 159 passed, 1 skipped (migration test needs `TEST_DATABASE_URL`) | Need auth, ownership, AI, GitHub, fix-workflow, notification and scheduling tests |
| Environment | Python 3.14 venv, Node 24, native PostgreSQL 18 service; Docker daemon not running; no `.env` files | Real-PostgreSQL migration test needs a disposable database URL from the developer |

## Key decisions

1. **Authentication**: done in FastAPI (the existing backend), not in Next.js.
   * Argon2id password hashes.
   * Short-lived HS256 access JWT (with a session ID claim checked against the database on every request, so revocation is immediate).
   * Opaque, rotating refresh token stored only as a SHA-256 hash; reuse of an old refresh token revokes the session.
   * Tokens live in `HttpOnly` cookies, and unsafe requests need a double-submit CSRF header.
   * The Next.js app proxies `/api/v1/*` to FastAPI through `rewrites`, so the browser only ever talks to one origin and cookies stay first-party.
2. **Ownership**: `projects.owner_id`. Every scan, finding, artifact, analysis, fix and pull request is reached through an owned project, and repository queries filter by owner. Other users' objects return 404 so their existence is not revealed.
   * Legacy projects created before authentication get `owner_id = NULL` and are hidden. They are not deleted: `python -m app.cli assign-orphans --email ...` assigns them to a user.
3. **Background jobs**: a generic `background_jobs` table processed by the existing worker process alongside scans. Jobs use the same atomic-claim, heartbeat, retry and idempotency rules. The scheduler also runs in the worker and claims due schedules with a conditional update so two workers cannot double-schedule.
4. **AI**: a provider abstraction (`AI_PROVIDER=anthropic|openai|gemini|none`) over plain HTTPS. Outputs are validated by Pydantic. Prompts mark website and repository content as untrusted data. With no key configured the API reports AI as unavailable; it never returns synthetic results.
5. **GitHub**: an OAuth App (authorization code flow with a `state` value bound to the user) and the REST API only. Tokens are encrypted at rest with Fernet (`TOKEN_ENCRYPTION_KEY`). Repositories are never cloned or executed. Files are fetched individually with size, count and path limits.
6. **Fixes**: AI proposes search-and-replace edits against fetched file contents. The server validates that each path was in the provided context and each `original` snippet matches exactly once. It then applies the edit in memory and runs a syntax check where one is available. Approved fixes are committed through the Git Data API to a new `fixify/…` branch, and a pull request is opened. Nothing is ever merged or pushed without explicit approval.

## Phases

0. Audit (this document)
1. Security foundation: users, sessions, CSRF, rate limiting, ownership on every query, email verification and password reset
2. Project editing, scan settings, per-user limits, additional scanner checks
3. AI provider layer, finding analysis jobs
4. GitHub OAuth, repository selection, file access
5. Fix generation, validation, diff review
6. Human review workflow, branch, commit, pull request
7. Analytics, notifications, scheduled scans
8. Premium UI: design system, landing page, application shell, all pages
9. Hardening, documentation, end-to-end verification

The final status and any limitations are reported in `docs/status.md` once the work is verified.
