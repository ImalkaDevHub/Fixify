# Authentication

Authentication is done by FastAPI, which owns the users, sessions, and data. The Next.js app is a client of the API.

## Decision

| Option | Why not / why |
|---|---|
| Auth in Next.js (e.g. Auth.js) | A second user store, with sessions FastAPI would have to trust indirectly. Rejected. |
| Bearer tokens in `localStorage` | Readable by any injected script. Rejected. |
| **FastAPI session cookies behind a same-origin rewrite** | `HttpOnly` cookies, a CSRF header, one source of truth. **Chosen.** |

The browser only talks to `http(s)://<web-app>/api/v1/*`. `next.config.ts` rewrites that path to `API_INTERNAL_URL`, so the cookies are first-party and no CORS credentials are needed. CORS stays enabled with credentials for the configured origins only, for direct calls during development.

## Cookies

| Cookie | Content | Flags |
|---|---|---|
| `fixify_access` | JWT `{sub, sid, typ, iss, iat, exp}`, 15 min | `HttpOnly; SameSite=Lax; Path=/api` (+ `Secure` in production) |
| `fixify_refresh` | Opaque 256-bit token | `HttpOnly; SameSite=Strict; Path=/api/v1/auth` |
| `fixify_csrf` | HMAC(SECRET_KEY, session ID) | Readable by JavaScript, echoed in `X-CSRF-Token` |
| `fixify_session` | `1` (no credential) | Lets `proxy.ts` redirect signed-out visitors |

The web client refreshes once on a 401 (one shared refresh for concurrent requests), then sends the visitor to `/login?next=…` if the refresh fails.

## Endpoints

| Method and path | Notes |
|---|---|
| `POST /auth/register` | Creates the account, signs in, and emails a verification link |
| `POST /auth/login` | Rate limited per IP and per account |
| `POST /auth/refresh` | Rotates the refresh token; reuse revokes the session |
| `POST /auth/logout` | Revokes the session and clears the cookies |
| `GET /auth/me` | The current user |
| `POST /auth/verify-email` · `POST /auth/resend-verification` | Single-use, 48 h |
| `POST /auth/forgot-password` · `POST /auth/reset-password` | Same answer whether or not the account exists; 30 min, single use; all sessions end |
| `PATCH /users/me` · `POST /users/me/password` · `DELETE /users/me` | Profile, password change (signs out other sessions), account deletion (password required) |
| `GET /users/me/sessions` · `DELETE /users/me/sessions/{id}` · `POST /users/me/sessions/revoke-others` | Session management |

## Email

- `EMAIL_BACKEND=console` (development): messages, including links, go to the API log.
- `smtp`: set `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, and `SMTP_STARTTLS`.
- `disabled`: messages are dropped (useful for tests).

Email is sent in a background task after the response, so response timing does not reveal whether an account exists.

## Email verification gate

With `REQUIRE_EMAIL_VERIFICATION=true` (the default), unverified users can sign in and create projects but cannot start scans, AI analysis, fix generation, GitHub connections, or pull requests. Scheduled scans of unverified owners are skipped, and the reason is recorded on the schedule.

## Existing data

Projects created before authentication have `owner_id = NULL` and are invisible. Assign them to an account:

```powershell
cd services/api
python -m app.cli assign-orphans --email you@example.com
```
