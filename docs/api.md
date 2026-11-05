# API reference

All endpoints are under `/api/v1`. The interactive OpenAPI docs are at `http://127.0.0.1:8000/docs` (disabled in production). Except for `health` and the public `auth` endpoints, every endpoint needs a session. Unsafe methods also need `X-CSRF-Token`. ✓ = requires a verified email.

Errors are JSON: `{"detail": "message"}`. Validation errors use FastAPI's list format.

| Area | Method and path | Notes |
|---|---|---|
| Health | `GET /health`, `GET /health/ready` | Readiness checks PostgreSQL (and Redis when it is the queue) |
| Auth | see [authentication.md](authentication.md) | |
| Projects | `GET /projects?search=&limit=&offset=`, `POST /projects`, `GET /projects/count`, `GET/PATCH/DELETE /projects/{id}` | Includes `latest_scan`; per-user project limit |
| | `GET /projects/{id}/verification`, `POST /projects/{id}/verification/check` ✓ | Ownership token and check (meta tag or `/.well-known` file) |
| Scans | `POST /projects/{id}/scans` ✓ | 202; 403 if ownership verification is required and missing; 409 if one is active; 429 at the per-user or global limit |
| | `GET /projects/{id}/scans`, `GET /scans`, `GET /scans/summary`, `GET /scans/{id}`, `POST /scans/{id}/cancel` | |
| | `GET /scans/{id}/findings?severity=`, `GET /scans/{id}/comparison`, `GET /scans/{id}/artifacts/{artifact_id}` | |
| Findings | `GET /findings?severity=&latest_only=`, `GET /projects/{id}/findings`, `GET /findings/{id}` | |
| AI | `GET /ai/status`, `GET /findings/{id}/ai`, `POST /findings/{id}/analysis` ✓ | 503 when AI is not configured |
| Jobs | `GET /jobs?subject_id=&active=`, `GET /jobs/{id}` | `queued`, `running`, `succeeded`, `failed` (with `error`) |
| GitHub | `GET /github/status`, `POST /github/connect` ✓, `POST /github/complete` ✓, `DELETE /github/connection` | |
| | `GET /github/repositories`, `GET /github/repositories/{owner}/{name}/branches` | |
| | `PUT/DELETE /projects/{id}/repository` ✓, `GET /projects/{id}/repository/tree?query=` | Verified with the user's token |
| Fixes | `POST /findings/{id}/fixes` ✓ | `{file_paths?, instructions?}` → job |
| | `GET /fixes?project_id=&finding_id=&status=`, `GET /fixes/{id}` | Detail includes changes, reviews, pull request |
| | `POST /fixes/{id}/reviews` ✓ | `{action: comment\|approve\|reject\|reopen, comment?}` |
| | `POST /fixes/{id}/regenerate` ✓, `POST /fixes/{id}/pull-request` ✓, `POST /fixes/{id}/pull-request/refresh` | Pull requests only from approved fixes |
| Notifications | `GET /notifications?unread_only=`, `POST /notifications/{id}/read`, `POST /notifications/read-all`, `GET/PUT /notifications/preferences` | |
| Schedules | `GET/PUT/DELETE /projects/{id}/schedule` | `{enabled, frequency: daily\|weekly\|custom, hour_utc, weekday, interval_hours}` |
| Analytics | `GET /analytics/overview?days=&project_id=` | Persisted data only |
