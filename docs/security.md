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

- A **nonce-based CSP** built per request in `proxy.ts` (`lib/csp.ts`): `script-src 'self' 'nonce-…' 'strict-dynamic'`, with no `'unsafe-inline'` for scripts and `'unsafe-eval'` only in development. Next.js adds the nonce to its own scripts, so every page renders per request (`connection()` in the root layout). `style-src` still allows `'unsafe-inline'`, because Motion and Recharts set inline `style` attributes, which nonces cannot cover; style injection cannot run code. Also `frame-ancestors 'none'`, `object-src 'none'`, `base-uri 'self'`, `form-action 'self'`, plus `nosniff`, `X-Frame-Options`, `Referrer-Policy`, and `Permissions-Policy`.
- The API adds `no-store`, `nosniff`, `X-Frame-Options`, and `Referrer-Policy` to every response. Screenshots are served with `default-src 'none'` and `Cross-Origin-Resource-Policy: same-origin`.
- Redirect targets after login and notification links accept only same-site paths.

## Known gaps

| # | Gap | Why it matters | Recommended solution | Blocks production? |
|---|---|---|---|---|
| 1 | **Browser isolation is in-process.** Chromium is constrained by the egress proxy and launch flags, not by an OS-level network policy, and the worker process holds database credentials. | A browser exploit on a malicious page could reach the internal network or the database. | Run the scanner in a container or VM whose network has internet egress only and no route to PostgreSQL, Redis, or the API. Split result persistence from browsing so the browsing container needs no database credentials. | **Yes**, for scanning untrusted public sites |
| 2 | **Ownership verification proves control of one page, not authorization.** No DNS TXT method. | Someone who can edit one page of a shared host (for example a hosted blog) can verify, and then scan, the whole host. | Add DNS TXT verification and require it for shared-hosting domains. | Yes, for a public multi-tenant service |
| 3 | **No second factor (2FA).** Login is protected by Argon2id and per-IP / per-account rate limits: 10 attempts per account per 15 minutes acts as a temporary lockout, shared across API processes through Redis. | A reused or phished password is enough to sign in. | TOTP 2FA with recovery codes, and notification of new sign-ins. | Recommended before public launch |
| 4 | **OAuth App `repo` scope is broad.** It is the narrowest OAuth-App scope that can push to private repositories (`public_repo` limits Fixify to public ones). | A leaked token grants access to all of the user's repositories, not just the connected one. Tokens are Fernet-encrypted at rest and revocable. | Move to a GitHub App with `contents:write`, `pull_requests:write` and `metadata:read` on selected repositories, using short-lived installation tokens. | Recommended |
| 5 | **AI fix validation is parse-only.** Full parsers cover JSON, Python, JavaScript/JSX, TypeScript/TSX and CSS. HTML-like files get tag balance; SCSS/Less get bracket balance. The parsers do not type-check, and tree-sitter accepts a mismatched JSX closing-tag name (`<div></span>`). | A proposed fix can parse and still be wrong. | Fixify never executes or merges fixes. Every change is human-reviewed and lands as a pull request, so the repository's CI must run on it. | No (by design) |
| 6 | **`style-src 'unsafe-inline'`** (see Web app above). | Lets injected markup restyle the page; it cannot run scripts. | Remove inline style attributes from the UI libraries, or accept it. | No |
| 7 | **Rate limits are per process without Redis.** Only with the fallback `QUEUE_BACKEND=database` and `REDIS_REQUIRED=false`. | Limits multiply with the number of API processes. | Keep Redis (the default). | No, with Redis |
| 8 | **Development email is written to the log.** `EMAIL_BACKEND=console` writes single-use links to the API log. | Anyone who can read the log can verify accounts or reset passwords. | It is refused in production; configure SMTP there. | No (refused in production) |
