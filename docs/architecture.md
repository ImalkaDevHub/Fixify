# Fixify architecture

## Components

- **Web (`apps/web`)**: App Router pages render the dashboard and project views. Client components use the centralized typed API client. Zod validation mirrors the backend project constraints.
- **API (`services/api/app`)**: versioned FastAPI routers validate HTTP requests and delegate to services. Services coordinate repository operations; repositories encapsulate SQL queries. Pydantic schemas define the API contract.
- **Persistence**: async SQLAlchemy sessions are injected per request. Alembic owns all schema changes. The initial `projects` table stores project metadata only.
- **Infrastructure (`infra`)**: Compose runs PostgreSQL and Redis with local-only port bindings, health checks, and persistent volumes. Redis is not yet used by application requests.

## Project creation request flow

1. The browser validates the project form with Zod.
2. The API client sends JSON to `POST /api/v1/projects`.
3. FastAPI/Pydantic validates the payload and injects an async database session.
4. The project service delegates persistence to the repository.
5. SQLAlchemy commits the project; the response schema serializes its UUID and timezone-aware timestamps.
6. The UI navigates to the returned project detail route and refreshes the list.

## Boundaries and future work

The current website URL validation checks syntax/protocol only. It is **not** safe to pass user URLs to a browser or network worker; implement SSRF defenses, DNS/IP checks, redirect controls, and network isolation before scanning. Browser automation and arbitrary execution should be isolated from the API process.

There is no authentication or user ownership. Add authentication, authorization, ownership filtering, rate limits, and dependent-record deletion policy before public deployment. Test runs, findings, GitHub connections, and AI services are intentionally outside this foundation.

Security requirements for later steps:

- Every project query must be scoped to an authenticated owner; today any caller can read or delete any project.
- Website pages and repository contents are untrusted input. Future AI analysis must treat them as data, never as instructions, and must not give model output direct access to credentials, the database, or the network.
- The browser worker must run in a separate, network-restricted process or container, never inside the API process.
