# Fixify security

Fixify loads arbitrary websites, sends evidence to an AI provider, and reads and writes external repositories. This document lists the controls and, just as importantly, the gaps.

## Authentication and sessions

- **Passwords.** Argon2id (64 MiB, 3 passes by default). Login failures give the same message and take the same time for unknown accounts. Common passwords and the email itself are refused.
- **Access token.** HS256 JWT, 15 minutes, in an `HttpOnly`, `SameSite=Lax` cookie scoped to `/api`. Each request also checks that the session it names still exists, has not expired, and has not been revoked, so logout and revocation take effect immediately.
- **Refresh token.** 256-bit opaque token, stored only as SHA-256, in an `HttpOnly`, `SameSite=Strict` cookie scoped to `/api/v1/auth`. It rotates on every use; presenting an already-rotated token revokes the whole session (theft detection).
- **CSRF.** Every unsafe, cookie-authenticated request needs the `X-CSRF-Token` header, whose value is an HMAC bound to the session, plus a trusted `Origin` when the browser sends one.
- **Single-use links.** Email verification and password reset tokens are hashed, expire, and are invalidated by a newer link. A password reset or change ends all other sessions. Links carry the token in the URL fragment, so it never reaches server or proxy logs.
- **Rate limits.** Login, registration, refresh, reset, verification, password changes, GitHub connects, and AI jobs per hour. Limits are shared through Redis when it is available, otherwise kept in process memory (see gaps).
- **Production guard.** With `APP_ENV=production` the API refuses to start with a short `SECRET_KEY`, `EMAIL_BACKEND=console`, `COOKIE_SECURE=false`, or `SCANNER_UNSAFE_ALLOWED_HOSTS`. It also disables `/docs`.

## Authorization

Every project has an owner. Scans, findings, screenshots, analyses, jobs, fixes, reviews, pull requests, and schedules are all reached through an owned project in the repository query itself, never filtered in the UI. Objects owned by someone else return **404**, exactly like missing ones. Starting scans, AI work, and GitHub actions also needs a verified email. The isolation suites are `tests/test_ownership.py` and `tests/test_ai_github_fixes.py`.

## Scanner isolation (SSRF)

Unchanged from step 2 and still enforced; see [scanner.md](scanner.md). In short:

- The URL policy is checked by the API, by the scanner, and by the egress proxy on every connection.
- Private, loopback, link-local, metadata, and internal hostnames are blocked.
- The proxy connects to the address it validated, which defeats DNS rebinding.
- The scanner runs in its own process without database or Redis credentials, with hard time limits.

## AI

- Website content and repository files are wrapped in `<untrusted_*>` blocks, and any embedded closing tags are neutralized. The system prompt says that nothing inside them is an instruction.
- High-confidence secret patterns (private keys, cloud and GitHub tokens, JWTs, `password = "..."` assignments) are replaced with `[REDACTED_SECRET]` before anything is sent. Edits that touch redacted text are rejected.
- Output is constrained by a JSON schema and validated again by Pydantic. File paths, related finding IDs, and edits are accepted only if they refer to content Fixify itself provided.
- The model cannot act. It only returns text that Fixify validates; it has no tools, network, or credentials.

## GitHub

- OAuth `state` is HMAC-signed, expires in 10 minutes, and is bound to the user and to an `HttpOnly` nonce cookie, so a leaked state cannot be completed by another account or browser.
- Tokens are encrypted with Fernet (`TOKEN_ENCRYPTION_KEY`, rotation supported) and never sent to the browser. Revoked tokens are detected (HTTP 401) and the connection is marked `revoked`. Disconnecting deletes the token and revokes the grant.
- **File access is allow-listed.** Only paths from the repository tree, normalized (no `..`, absolute paths, backslashes, or `.git`), with source extensions. Secrets files, keys, lock files, `node_modules`, build output, and minified bundles are never read. Size, count, and total-byte limits apply. Repositories are never cloned and nothing from them is executed (syntax checks only parse).
- **Writes are limited.** New blobs on a new `fixify/…` branch, then a pull request, and only after explicit approval. Never a push to an existing branch, never a merge. Website-derived text in pull request bodies has `@` mentions neutralized.

## Website ownership verification

With `REQUIRE_SITE_VERIFICATION` (default: on in production), a project's host must publish a token before it can be scanned. The token goes either in `<meta name="fixify-site-verification" content="…">` on the home page or in `/.well-known/fixify-verification.txt`.

- The check runs through the scanner's egress proxy, with the same SSRF policy.
- It follows only same-host redirects and reads bounded bodies.
- Verification is bound to the hostname. Changing the website to another host clears it, and scans (including a `target_url` override and scheduled scans) must stay on the verified host.

## Web app

- A CSP with `frame-ancestors 'none'`, plus `nosniff`, `X-Frame-Options`, `Referrer-Policy`, and `Permissions-Policy`.
- The API adds `no-store`, `nosniff`, `X-Frame-Options`, and `Referrer-Policy` to every response. Screenshots are served with `default-src 'none'` and `Cross-Origin-Resource-Policy: same-origin`.
- Redirect targets after login and notification links accept only same-site paths.

## Known gaps (not production-ready until addressed)

1. **Browser isolation is in-process.** Chromium is constrained by the egress proxy and launch flags, not by an OS-level network policy. For untrusted public use, run the worker in a container or VM whose network has internet egress only and no route to PostgreSQL, Redis, or the API. Until result persistence is split from browsing, the worker container still needs database access.
2. **Ownership verification proves control, not authorization.** It is on by default in production (`REQUIRE_SITE_VERIFICATION`), and it shows that someone can publish content on the host. That is stronger than nothing, but a user who can edit one page of a shared host (for example a hosted blog) can verify the whole host. DNS TXT verification is not implemented.
3. **In-memory rate limits without Redis.** With `QUEUE_BACKEND=database` and no Redis, limits apply per API process only.
4. **The CSP allows `'unsafe-inline'` scripts** (Next.js hydration). A nonce-based CSP via `proxy.ts` would be stronger.
5. **The OAuth App `repo` scope is broad.** It is the narrowest scope that can push to private repositories. A GitHub App with `contents:write` and `pull_requests:write` on selected repositories would be more granular.
6. **No account lockout or second factor.** Only rate limits and Argon2 slow down attacks on the login.
7. **Development email is printed to the log.** `EMAIL_BACKEND=console` writes single-use links to the API log, so it is refused in production.
