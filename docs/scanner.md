# Fixify scanner (Step 2)

The scanner opens a project's website in headless Chromium, runs a fixed catalog of rule-based checks, and stores what it observed. It does not use AI, does not execute repository code, and does not modify websites.

## Processes

| Process | Command | Has database credentials | Runs a browser |
|---|---|---|---|
| API | `uvicorn app.main:app` | yes | **no** |
| Worker | `python -m app.worker` | yes | no |
| Scanner (one per scan) | `python -m app.scanner`, started by the worker | **no** | yes |

The worker starts the scanner with an explicit allowlist of environment variables (`PATH`, temp directories, the Playwright browser path, and similar). `DATABASE_URL`, `REDIS_URL`, and every other setting are not passed. The `app.scanner` package never imports application settings, so it never reads `.env`. Chromium is launched with an even smaller environment. The job is sent as JSON on stdin and the result returned as JSON on stdout.

The worker kills the scanner's whole process tree (`taskkill /T` on Windows, a process group on Linux/macOS) if it runs 30 s past `SCANNER_MAX_SCAN_DURATION_SECONDS`, or when the worker shuts down. The scanner itself closes its browser context and browser in `finally` blocks.

## Scan lifecycle

1. `POST /api/v1/projects/{id}/scans` validates the project and options, checks the target URL against the URL policy, rejects a second active scan for the same project (409) or too many active scans overall (429), creates a `test_runs` row with status `queued`, and enqueues the run ID. It returns **202**.
2. If enqueueing fails (Redis down), the run is immediately marked `failed` with a reason and the API returns **503**. No orphaned `queued` run is left behind.
3. A worker receives the ID from Redis, or finds queued runs by polling PostgreSQL (every `WORKER_POLL_INTERVAL_SECONDS`; this also recovers lost messages, and it is the only mechanism when `QUEUE_BACKEND=database`).
4. The worker claims the run with one conditional update: `queued → running`, `attempts + 1`. Only one worker can win; duplicate messages fail to claim and are ignored. Cancelled runs are never claimed.
5. While scanning, the worker refreshes `heartbeat_at` every 15 s.
6. The result, check rows, findings, artifacts, counters, and the terminal status are written in **one transaction**, and only if the run is still `running` with the same attempt number. Results of an earlier attempt are deleted first, so retries never duplicate findings.
7. If the scanner process crashes or times out, the run goes back to `queued` until `SCAN_MAX_ATTEMPTS` is reached, then to `failed`.
8. If a worker dies, the run's heartbeat stops. Any worker re-queues (or, after the last attempt, fails) runs whose heartbeat is older than 90 s. A run therefore never stays `running` indefinitely.
9. On Ctrl+C, a worker kills its scanners and returns its in-flight runs to `queued`.

This is **at-least-once execution with idempotent result storage**. A scan may run twice after a crash; only one result is stored. It is not exactly-once execution.

Only `queued` scans can be cancelled (`POST /api/v1/scans/{id}/cancel`). Running scans cannot be cancelled in this step.

### Run statuses

| Status | Meaning |
|---|---|
| `queued` | Waiting for a worker |
| `running` | Claimed by a worker |
| `completed` | Every check ran. Findings may exist: a website with bugs is still a completed scan |
| `completed_with_errors` | The scan finished but at least one check could not run (for example the screenshot failed) |
| `failed` | Infrastructure failure: queue unavailable, scanner crashed, target blocked by policy, or the scan exceeded its time limit |
| `cancelled` | Cancelled before it started |

A website that times out or cannot be reached is a **finding** (`critical`) in a `completed` scan, not a failed scan.

## Data model

```text
projects 1──* test_runs 1──* test_case_results   (one row per check, unique per run)
                       1──* findings             (unique per run + fingerprint)
                       1──* scan_artifacts       (screenshot metadata; file on disk)
projects 1──* findings / scan_artifacts          (project_id stored for fast project queries)
```

Deleting a project cascades to its runs, checks, findings, and artifact rows, and the API removes the artifact files. Evidence and check details are `JSONB` in PostgreSQL. Findings carry a `fingerprint` (a hash of the finding type and its normalized subject, such as the URL without query string) used for deduplication and for comparing scans; `first_detected_at` is the first time that fingerprint was seen in the project.

## Checks and severity rules

| Check | Finding types | Severity |
|---|---|---|
| Page navigation | `navigation_timeout`, `navigation_error` (DNS, connection, TLS), `navigation_blocked` (target redirected to a blocked address), `http_error_document` | critical, critical, high, high for 404/410/5xx and medium for other 4xx |
| Console errors | `console_error` | medium |
| Uncaught exceptions | `uncaught_exception` | high |
| Failed requests | `network_failure`, `request_blocked` | first-party script/stylesheet high, first-party fetch/xhr/sub-document medium, everything else low; policy blocks are info |
| HTTP errors | `http_error_resource` | first-party script/stylesheet high; first-party fetch/xhr 5xx high, 401/403 low, other 4xx medium; third-party low (medium for third-party script/stylesheet 5xx) |
| Broken links | `broken_link` (confirmed), `possibly_broken_link` (suspected) | confirmed: medium same-site, low external; suspected: low |
| Screenshot | none (the check reports `error` if capture fails) | — |
| Basic page checks | `missing_title`, `missing_viewport_meta`, `missing_h1`, `missing_favicon` | low, low, info, info |

Explicit, documented exclusion rules:

- Console messages starting with `Failed to load resource:` are ignored by the console check, because Chromium logs one for every failed sub-resource and the network checks report those with more context.
- Requests failing with `net::ERR_ABORTED` (navigation away, aborted fetches, media range requests) are not findings.
- Console warnings and informational messages are never findings.
- Broken-link results of 400/401/403/405/406/429/451/999, timeouts, and connection errors are recorded as *inconclusive* in the check details, not as findings. Only 404/410 are confirmed. 5xx and DNS failures are *suspected*.
- The favicon finding is reported only when the page declares no icon **and** `/favicon.ico` returns 404/410.

The basic page checks are indicators, not an accessibility or SEO audit.

## Evidence and artifacts

Stored evidence is bounded (messages 1,000 characters, stacks 4,000, each evidence object 16 KB) and passed through redaction: URL credentials and fragments are removed, query parameters whose names look secret (`token`, `key`, `session`, `code`, `password`, ...) are replaced with `[redacted]`, bearer tokens and JWT-shaped strings in text are redacted, `data:`/`blob:` URLs are reduced to their scheme, and control characters are stripped.

Never collected: cookies, request or response headers, local/session storage, page HTML, response bodies, downloads, or environment variables. Service workers and downloads are disabled in the browser context, and every scan uses a fresh, non-persistent context.

Screenshots are viewport-sized PNGs (`SCANNER_VIEWPORT_WIDTH` × `SCANNER_VIEWPORT_HEIGHT`, default 1280×800), discarded if larger than `ARTIFACT_MAX_BYTES`. They are stored as `ARTIFACT_DIR/<run id>/<artifact id>.png`, names generated by the server. The API serves an artifact only by `(run id, artifact id)` looked up in the database, resolves the stored key against the artifact directory and refuses anything that is not `<uuid>/<uuid>.png` or that resolves outside it, and responds with `X-Content-Type-Options: nosniff` and `Content-Security-Policy: default-src 'none'`.

Retention: the worker deletes run folders older than `ARTIFACT_RETENTION_DAYS` (default 14) and folders whose run no longer exists, at start-up and hourly. Database rows are kept; the report then shows that the screenshot is no longer available. To clean up manually, stop the worker and delete folders under `services/api/.artifacts`.

## URL safety policy (SSRF)

Enforced in `app/scanner/url_policy.py` and applied:

1. by the API before a scan is queued (fast feedback, `422`),
2. by the scanner before launching the browser, and
3. by the **egress proxy** (`app/scanner/egress_proxy.py`) on **every connection** the browser or the link checker opens.

Rules:

- Only `http` and `https`; URLs with embedded credentials are refused.
- Ports limited to `SCANNER_ALLOWED_PORTS` (default 80, 443, 8080, 8443).
- Refused host names: `localhost`, `*.localhost`, `*.local`, `*.localdomain`, `*.internal` (including `metadata.google.internal`), `*.intranet`, `*.lan`, `*.home`, `*.home.arpa`, `*.corp`, `*.private`, and every single-label name (`postgres`, `redis`, `api`, ...).
- IP literals in any form, including legacy numeric forms such as `2130706433` and `0x7f.1`, are parsed and checked.
- Host names are resolved and **every** returned address must be public. Refused: loopback, private (RFC 1918, ULA), link-local (including `169.254.169.254` cloud metadata and `fd00:ec2::254`), carrier-grade NAT, multicast, reserved, unspecified, benchmarking ranges, IPv4-mapped/6to4/NAT64 forms of those, and anything Python does not consider globally routable.
- The proxy connects to the exact address it validated, so a second DNS answer cannot redirect the connection (DNS rebinding between check and use).
- Redirects are new requests through the proxy, so every hop is checked. The link checker follows at most 5 redirects manually.
- Chromium's implicit proxy bypass for loopback is disabled (`<-loopback>`), and WebRTC is restricted to proxied connections so it cannot open direct UDP connections.

### Known limitations

These are deliberate, documented gaps, not claims of complete protection:

- **Network isolation is in-process.** The browser is restricted by the proxy and its launch flags, not by an OS or container firewall. A Chromium vulnerability or a protocol that ignores proxy settings could bypass the policy. For stronger isolation, run the worker container on a network that only has internet egress and no route to PostgreSQL, Redis, or the API (the provided Compose file puts the worker on the default network so it can reach the database; splitting result persistence from browsing is a later step).
- **The worker process holds database credentials.** Only the scanner process and Chromium are started without them.
- **DNS answers are trusted at resolution time.** An attacker-controlled public DNS name can still point at any *public* address.
- **No authorization.** The policy decides *where* the scanner may connect, not *whether the user is allowed to scan that website*. Ownership verification (for example a DNS TXT or file challenge) is not implemented. Only scan websites you are authorized to test.
- **`SCANNER_UNSAFE_ALLOWED_HOSTS` disables the private-address check for exact `host:port` pairs.** It exists for local fixtures and must stay empty anywhere else.
- The Docker worker image and its resource limits have not yet been exercised by an actual container build in this repository's checks.

## Limits

| Setting | Default | Hard cap |
|---|---|---|
| `SCANNER_MAX_SCAN_DURATION_SECONDS` | 180 | 900 |
| `SCANNER_NAVIGATION_TIMEOUT_SECONDS` | 30 | 120 |
| `SCANNER_MAX_LINKS` (per scan; requests may ask for fewer) | 25 | 200 |
| `SCANNER_LINK_CONCURRENCY` | 4 | 10 |
| `SCANNER_LINK_TIMEOUT_SECONDS` | 8 | 30 |
| `SCANNER_MAX_QUEUED_SCANS` (queued + running, all projects) | 20 | 500 |
| `ARTIFACT_MAX_BYTES` | 5,000,000 | 20,000,000 |
| `WORKER_CONCURRENCY` | 1 | 4 |
| `SCAN_MAX_ATTEMPTS` | 2 | 5 |

Each Playwright event type is capped at 500 recorded events per scan, and pages are scanned at most once per run (no crawling).

## Tests

- `tests/test_url_policy.py`: prohibited and allowed destinations with fake DNS (no network).
- `tests/test_scanner_rules.py`: severity rules, deduplication, sanitization, link classification, artifact path validation, retention.
- `tests/test_scanner_engine.py`: the egress proxy and real headless Chromium against `tests/fixtures/scan_site.py` (success, 404, 500, console error, uncaught exception, failed and blocked scripts, broken links, missing title, navigation timeout, screenshot, redirect to an internal address), plus the real scanner subprocess.
- `tests/test_scans_api.py`: scan endpoints, queue failure, pagination, filtering, artifact access restrictions, comparison, cancellation, readiness.
- `tests/test_worker.py`: claiming, duplicate delivery, bounded retries, stale-run recovery, idempotent persistence, scanner environment.

The scanner tests need `python -m playwright install chromium` and are skipped without it. None of them reaches the internet.
