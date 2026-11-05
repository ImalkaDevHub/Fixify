# Deployment

> Read [security.md](security.md) → "Known gaps" first. Fixify is not ready for anonymous public sign-up until those gaps are closed.

## Topology

```text
internet ─► TLS reverse proxy ─► web (next start :3000) ─► api (python -m app.serve :8000, private)
                                                            │
                                     PostgreSQL ◄───────────┼──► worker (python -m app.worker)
                                     Redis (recommended) ◄──┘        └─► scanner subprocess ─► internet only
```

## Checklist

1. `APP_ENV=production`. The API refuses unsafe settings at startup.
2. `SECRET_KEY`: at least 32 random characters, the same for every API instance.
3. `PUBLIC_APP_URL=https://your-domain` and `API_CORS_ORIGINS=https://your-domain`.
4. TLS at the edge. Cookies are `Secure` in production.
5. `EMAIL_BACKEND=smtp` with real SMTP credentials.
6. PostgreSQL with `sslmode=require`, then run `alembic upgrade head` from `services/api` before starting the new version.
7. Redis (`QUEUE_BACKEND=redis`) so rate limits are shared between API instances.
8. `TOKEN_ENCRYPTION_KEY`, the GitHub OAuth app (callback `https://your-domain/github/callback`), and `ANTHROPIC_API_KEY`, as needed.
9. The API listens privately. Set `FORWARDED_ALLOW_IPS` to the web tier's address so client IPs (used for rate limits) are trusted only from there.
10. Run the worker with `Dockerfile.worker` (unprivileged user, dropped capabilities, resource limits) on a network that can reach the internet and the database, but not the API or other internal services.
11. Back up PostgreSQL and the artifact directory. Screenshots are kept for `ARTIFACT_RETENTION_DAYS`.
12. Build the web app with `API_INTERNAL_URL` pointing at the private API address (rewrites are fixed at build time).

> [!NOTE]
> The artifact directory remembers its database (`.fixify-database`). A worker pointed at another database skips cleanup instead of deleting that environment's screenshots. Still, use one `ARTIFACT_DIR` per environment.

Website ownership verification is required by default in production (`REQUIRE_SITE_VERIFICATION`). Users publish a meta tag or a `/.well-known` file before their first scan.

## Docker Compose (single host)

```powershell
docker compose --env-file .env -f infra/docker-compose.yml --profile worker --profile app up -d --build
docker compose --env-file .env -f infra/docker-compose.yml run --rm api alembic upgrade head
```

The API and web containers in `infra/docker-compose.yml` have not been built in this repository's checks (no Docker daemon was available). Verify them in your environment before relying on them.
