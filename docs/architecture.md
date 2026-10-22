# Fixify architecture

## Components

- **Web (`apps/web`)**: App Router pages render the dashboard, projects, scan reports (`/scans/[runId]`), and findings (`/findings/[findingId]`). Client components use the centralized typed API client (`lib/api.ts`). Scan status updates use a bounded, non-overlapping polling hook (`lib/use-polling.ts`) that stops on terminal states, on unmount, after repeated errors, or after 15 minutes. Zod validation mirrors the backend project constraints.
- **API (`services/api/app`)**: versioned FastAPI routers validate HTTP requests and delegate to services. Services coordinate repository operations; repositories encapsulate SQL queries. Pydantic schemas define the API contract. The API never launches a browser.
- **Worker (`app/worker`)**: claims queued scan runs, starts the scanner process, enforces the hard time limit, records heartbeats, retries crashed attempts, recovers runs from dead workers, writes results in one transaction, and applies artifact retention.
- **Scanner (`app/scanner`)**: an isolated process (`python -m app.scanner`) started without database or Redis credentials. It enforces the URL policy through a local egress proxy, drives headless Chromium with Playwright, and returns a typed `ScanResult`. Its modules are separately testable: `url_policy`, `egress_proxy`, `links`, `checks` (pure rules), `classify` (severity, fingerprints, deduplication), `sanitize`, `engine` (Playwright orchestration), `contract` (types).
- **Persistence**: async SQLAlchemy sessions; Alembic owns all schema changes (`0001_projects`, `0002_scans`). Tables: `projects`, `test_runs`, `test_case_results`, `findings`, `scan_artifacts`. Evidence uses JSONB.
- **Infrastructure (`infra`)**: Compose runs PostgreSQL and Redis with local-only port bindings, health checks, and persistent volumes, plus an opt-in `worker` service (profile `worker`) with resource and privilege limits.

## Project creation request flow

1. The browser validates the project form with Zod.
2. The API client sends JSON to `POST /api/v1/projects`.
3. FastAPI/Pydantic validates the payload and injects an async database session.
4. The project service delegates persistence to the repository.
5. SQLAlchemy commits the project; the response schema serializes its UUID and timezone-aware timestamps.
6. The UI navigates to the returned project detail route.

## Scan request flow

1. **Run scan** sends `POST /api/v1/projects/{id}/scans`.
2. The API checks the project, the URL policy, and the active-scan limits, creates a `queued` run, enqueues its ID (Redis, or nothing with `QUEUE_BACKEND=database`), and returns `202`. A queue failure marks the run `failed` and returns `503`.
3. A worker claims the run atomically (`queued → running`), builds a `ScanJob`, and runs `python -m app.scanner` with a minimal environment.
4. The scanner starts the egress proxy and Chromium, navigates, observes events, runs the checks, captures a screenshot, validates links, and prints a `ScanResult`.
5. The worker copies the screenshot into the artifact store and writes checks, findings, artifact rows, counters, and the terminal status in one transaction.
6. The frontend polls `GET /api/v1/scans/{id}` until the status is terminal, then loads findings and the comparison with the previous scan.

The full lifecycle, data model, check catalog, and security boundaries are in [scanner.md](scanner.md).

## API

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/v1/projects/{project_id}/scans` | Queue a scan (`202`) |
| `GET` | `/api/v1/projects/{project_id}/scans` | Scan history, newest first, paginated |
| `GET` | `/api/v1/projects/{project_id}/findings` | Findings across scans, `severity` filter, paginated |
| `GET` | `/api/v1/scans/summary` | Dashboard counts |
| `GET` | `/api/v1/scans/{run_id}` | Status, counters, checks, artifacts |
| `POST` | `/api/v1/scans/{run_id}/cancel` | Cancel a queued scan |
| `GET` | `/api/v1/scans/{run_id}/findings` | Findings of one scan, most severe first, `severity` filter |
| `GET` | `/api/v1/scans/{run_id}/comparison` | New / no longer seen / unchanged vs. the previous finished scan |
| `GET` | `/api/v1/scans/{run_id}/artifacts/{artifact_id}` | Serve an artifact that belongs to that scan |
| `GET` | `/api/v1/findings/{finding_id}` | One finding with sanitized evidence |
| `GET` | `/api/v1/health/ready` | PostgreSQL, plus Redis when it is the queue |

Project list and detail responses include `latest_scan` (status, time, findings count). All endpoints are documented in the OpenAPI schema at `/docs`.

## Boundaries and future work

There is no authentication or user ownership: anyone who can reach the API can create projects, start scans, and read every result. Add authentication, authorization, ownership filtering, ownership verification of scanned websites, and rate limits before any shared or public deployment.

Security requirements for later steps:

- Every project, scan, finding, and artifact query must be scoped to an authenticated owner.
- Website pages and repository contents are untrusted input. Future AI analysis must treat them as data, never as instructions, and must not give model output direct access to credentials, the database, or the network.
- Move browsing to a container or VM whose network has internet egress only, and separate result persistence from the process that browses (see the limitations in [scanner.md](scanner.md)).
