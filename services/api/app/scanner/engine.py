"""Playwright scan engine: drives Chromium, records events, and runs the check catalog."""

import asyncio
import contextlib
import hashlib
import logging
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Page, Request, Response, async_playwright
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from app.scanner import checks
from app.scanner.checks import (
    ConsoleEvent,
    NavigationOutcome,
    PageErrorEvent,
    PageSnapshot,
    RequestFailureEvent,
    ResponseErrorEvent,
    Window,
)
from app.scanner.classify import FindingCollector
from app.scanner.contract import ArtifactResult, CheckResult, ScanJob, ScanResult
from app.scanner.egress_proxy import PROXY_HEADER, EgressProxy
from app.scanner.links import LinkChecker, select_links
from app.scanner.sanitize import clean_text, redact_url
from app.scanner.url_policy import BlockedDestinationError, UrlPolicy, split_http_url

logger = logging.getLogger(__name__)

SCREENSHOT_FILE = "screenshot.png"
_MAX_EVENTS = 500  # per event type; a page spamming errors cannot exhaust memory
_SETTLE_TIMEOUT_MS = 5_000
_SCREENSHOT_TIMEOUT_MS = 10_000
_BROWSER_ENV_KEYS = ("SYSTEMROOT", "SystemRoot", "WINDIR", "TEMP", "TMP", "HOME", "LANG", "TZ")
_CHROMIUM_ARGS = [
    # WebRTC could otherwise open UDP connections that bypass the egress proxy.
    "--force-webrtc-ip-handling-policy=disable_non_proxied_udp",
    "--webrtc-ip-handling-policy=disable_non_proxied_udp",
    "--disable-background-networking",
    "--dns-prefetch-disable",
    "--no-pings",
    "--disable-features=InterestFeedContentSuggestions,MediaRouter",
]
_PAGE_SNAPSHOT_JS = """() => ({
  title: document.title,
  h1Count: document.querySelectorAll('h1').length,
  hasViewportMeta: !!document.querySelector('meta[name="viewport" i]'),
  iconDeclared: !!document.querySelector('link[rel~="icon" i]'),
  hrefs: Array.from(document.querySelectorAll('a[href]'), (a) => String(a.href).slice(0, 2048))
    .slice(0, 2000),
})"""

CHECK_NAMES = {
    "page_navigation": "Page navigation",
    "console_errors": "JavaScript console errors",
    "uncaught_exceptions": "Uncaught JavaScript exceptions",
    "failed_requests": "Failed network requests",
    "http_errors": "HTTP error responses",
    "page_basics": "Basic page checks",
    "screenshot": "Screenshot",
    "broken_links": "Broken links",
}


def browser_env() -> dict[str, str]:
    """Only the variables Chromium needs to start; no credentials or application settings."""
    return {key: os.environ[key] for key in _BROWSER_ENV_KEYS if key in os.environ}


def _now() -> datetime:
    return datetime.now(UTC)


class _EventRecorder:
    def __init__(self, proxy: EgressProxy) -> None:
        self.proxy = proxy
        self.console: list[ConsoleEvent] = []
        self.page_errors: list[PageErrorEvent] = []
        self.failures: list[RequestFailureEvent] = []
        self.responses: list[ResponseErrorEvent] = []

    def attach(self, page: Page) -> None:
        page.on("console", self._on_console)
        page.on("pageerror", self._on_page_error)
        page.on("requestfailed", self._on_request_failed)
        page.on("response", self._on_response)

    def _proxy_reason(self, url: str) -> str | None:
        parts = urlsplit(url)
        if not parts.hostname:
            return None
        port = parts.port or (443 if parts.scheme == "https" else 80)
        return self.proxy.events.reason_for(parts.hostname, port)

    def _on_console(self, message) -> None:  # noqa: ANN001 - Playwright ConsoleMessage
        if message.type != "error" or len(self.console) >= _MAX_EVENTS:
            return
        location = message.location or {}
        self.console.append(
            ConsoleEvent(
                text=clean_text(message.text),
                url=location.get("url") or None,
                line=location.get("lineNumber"),
                column=location.get("columnNumber"),
            )
        )

    def _on_page_error(self, error: PlaywrightError) -> None:
        if len(self.page_errors) < _MAX_EVENTS:
            self.page_errors.append(
                PageErrorEvent(message=error.message, name=error.name, stack=error.stack)
            )

    def _on_request_failed(self, request: Request) -> None:
        if len(self.failures) >= _MAX_EVENTS:
            return
        frame_url = None
        with contextlib.suppress(PlaywrightError):
            frame_url = request.frame.url
        self.failures.append(
            RequestFailureEvent(
                url=request.url,
                method=request.method,
                resource_type=request.resource_type,
                failure=request.failure or "unknown",
                frame_url=frame_url,
                proxy_reason=self._proxy_reason(request.url),
            )
        )

    def _on_response(self, response: Response) -> None:
        proxy_reason = response.headers.get(PROXY_HEADER)
        if response.status < 400 and not proxy_reason:
            return
        request = response.request
        frame_url = None
        with contextlib.suppress(PlaywrightError):
            frame_url = request.frame.url
        if proxy_reason:
            # The proxy answered, not the website: this is a network-level failure.
            if len(self.failures) < _MAX_EVENTS:
                self.failures.append(
                    RequestFailureEvent(
                        url=response.url,
                        method=request.method,
                        resource_type=request.resource_type,
                        failure=proxy_reason,
                        frame_url=frame_url,
                        proxy_reason=proxy_reason,
                    )
                )
            return
        if len(self.responses) >= _MAX_EVENTS:
            return
        self.responses.append(
            ResponseErrorEvent(
                url=response.url,
                status=response.status,
                method=request.method,
                resource_type=request.resource_type,
                frame_url=frame_url,
                proxy_reason=proxy_reason,
            )
        )


class ScanEngine:
    def __init__(self, job: ScanJob, policy: UrlPolicy | None = None) -> None:
        self.job = job
        self.limits = job.limits
        self.policy = policy or UrlPolicy(job.policy)
        self.output_dir = Path(job.output_dir)
        self.collector = FindingCollector()
        self.checks: dict[str, CheckResult] = {}
        self.artifacts: list[ArtifactResult] = []
        self.final_url: str | None = None

    async def run(self) -> ScanResult:
        started = _now()
        outcome_failure: str | None = None
        try:
            split_http_url(self.job.target_url)
            await self.policy.check_url(self.job.target_url)
        except BlockedDestinationError as error:
            return self._result(started, f"Target blocked by the scanner safety policy: {error}")
        except ValueError:
            pass  # unresolvable hosts are scanned and reported as a navigation finding

        try:
            await asyncio.wait_for(self._scan(), timeout=self.limits.max_scan_duration_seconds)
        except TimeoutError:
            outcome_failure = (
                f"The scan exceeded the maximum duration of "
                f"{self.limits.max_scan_duration_seconds} s."
            )
        except PlaywrightError as error:
            logger.warning("Browser failure: %s", clean_text(error.message, 300))
            outcome_failure = "The browser failed while scanning. See the worker log for details."
        return self._result(started, outcome_failure)

    def _result(self, started: datetime, failure: str | None) -> ScanResult:
        finished = _now()
        target = self.job.target_url
        for check_type, name in CHECK_NAMES.items():
            if check_type not in self.checks:
                reason = "Not run because the scan did not complete." if failure else "Not run."
                self.checks[check_type] = checks.skipped(name, check_type, target, reason, finished)
        results = list(self.checks.values())
        if failure:
            outcome = "failed"
        elif any(check.status == "error" for check in results):
            outcome = "completed_with_errors"
        else:
            outcome = "completed"
        return ScanResult(
            requested_url=redact_url(target) or target,
            final_url=redact_url(self.final_url),
            started_at=started,
            finished_at=finished,
            outcome=outcome,
            checks=results,
            findings=self.collector.all(),
            artifacts=self.artifacts,
            failure_reason=failure,
        )

    async def _scan(self) -> None:
        proxy = EgressProxy(self.policy)
        await proxy.start()
        try:
            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch(
                    headless=True,
                    proxy={"server": proxy.url, "bypass": "<-loopback>"},
                    args=_CHROMIUM_ARGS,
                    env=browser_env(),
                )
                try:
                    context = await browser.new_context(
                        viewport={
                            "width": self.limits.viewport_width,
                            "height": self.limits.viewport_height,
                        },
                        service_workers="block",
                        accept_downloads=False,
                        ignore_https_errors=False,
                        java_script_enabled=True,
                    )
                    try:
                        await self._scan_page(await context.new_page(), proxy)
                    finally:
                        with contextlib.suppress(PlaywrightError):
                            await context.close()
                finally:
                    with contextlib.suppress(PlaywrightError):
                        await browser.close()
        finally:
            await proxy.close()

    async def _scan_page(self, page: Page, proxy: EgressProxy) -> None:
        target = self.job.target_url
        recorder = _EventRecorder(proxy)
        recorder.attach(page)
        observe_start = _now()

        nav = await self._navigate(page, recorder)
        self.final_url = nav.final_url
        self.checks["page_navigation"] = checks.check_navigation(
            nav, self.collector, Window(observe_start, _now())
        )
        if not nav.document_loaded:
            reason = "Skipped because the page could not be loaded."
            for check_type in CHECK_NAMES:
                if check_type not in self.checks:
                    self.checks[check_type] = checks.skipped(
                        CHECK_NAMES[check_type], check_type, target, reason, _now()
                    )
            return

        with contextlib.suppress(PlaywrightError):
            await page.wait_for_load_state("networkidle", timeout=_SETTLE_TIMEOUT_MS)
        page_url = nav.final_url or target
        snapshot = await self._snapshot(page)

        window = Window(observe_start, _now())
        self.checks["console_errors"] = checks.check_console(
            recorder.console, page_url, self.collector, window
        )
        self.checks["uncaught_exceptions"] = checks.check_exceptions(
            recorder.page_errors, page_url, self.collector, window
        )
        self.checks["failed_requests"] = checks.check_failed_requests(
            recorder.failures, page_url, self.collector, window
        )
        self.checks["http_errors"] = checks.check_http_errors(
            recorder.responses, page_url, nav.final_url, self.collector, window
        )

        self.checks["screenshot"] = await self._screenshot(page, page_url)

        async with LinkChecker(
            proxy.url,
            timeout_seconds=self.limits.link_timeout_seconds,
            concurrency=self.limits.link_concurrency,
        ) as link_checker:
            started = _now()
            favicon_status = None
            if snapshot is not None and not snapshot["iconDeclared"]:
                parts = urlsplit(page_url)
                favicon = await link_checker.check(f"{parts.scheme}://{parts.netloc}/favicon.ico")
                favicon_status = favicon.status
            if snapshot is None:
                self.checks["page_basics"] = self._error_check(
                    "page_basics", page_url, "The page content could not be inspected.", started
                )
            else:
                self.checks["page_basics"] = checks.check_page_basics(
                    PageSnapshot(
                        title=snapshot["title"],
                        h1_count=int(snapshot["h1Count"]),
                        has_viewport_meta=bool(snapshot["hasViewportMeta"]),
                        icon_declared=bool(snapshot["iconDeclared"]),
                        favicon_status=favicon_status,
                    ),
                    page_url,
                    self.collector,
                    Window(started, _now()),
                )

            started = _now()
            if snapshot is None or self.limits.max_links == 0:
                self.checks["broken_links"] = checks.skipped(
                    CHECK_NAMES["broken_links"],
                    "broken_links",
                    page_url,
                    "Link checking is disabled for this scan."
                    if self.limits.max_links == 0
                    else "Links could not be collected from the page.",
                    started,
                )
            else:
                links, found = select_links(snapshot["hrefs"], page_url, self.limits.max_links)
                results = await link_checker.check_all(links)
                self.checks["broken_links"] = checks.check_links(
                    results, found, page_url, self.collector, Window(started, _now())
                )

    async def _navigate(self, page: Page, recorder: _EventRecorder) -> NavigationOutcome:
        target = self.job.target_url
        nav = NavigationOutcome(requested_url=target)
        started = time.monotonic()
        try:
            response = await page.goto(
                target,
                wait_until="load",
                timeout=self.limits.navigation_timeout_seconds * 1000,
            )
        except PlaywrightTimeoutError:
            nav.error_kind = "timeout"
            nav.error_message = "Navigation timeout"
        except PlaywrightError as error:
            nav.error_message = clean_text(error.message.split("\n", 1)[0], 300)
            nav.error_kind = self._navigation_failure_kind(error.message, recorder)
        else:
            if response is None:
                nav.error_kind = "browser_error"
                nav.error_message = "The browser returned no response for the page."
            else:
                proxy_reason = response.headers.get(PROXY_HEADER)
                chain: list[str] = []
                previous = response.request.redirected_from
                while previous is not None and len(chain) < 10:
                    chain.insert(0, previous.url)
                    previous = previous.redirected_from
                nav.redirect_chain = chain
                nav.final_url = response.url
                if proxy_reason:
                    nav.error_kind = proxy_reason
                    nav.error_message = f"Scanner proxy: {proxy_reason}"
                else:
                    nav.status = response.status
        nav.duration_ms = int((time.monotonic() - started) * 1000)
        if nav.final_url is None:
            with contextlib.suppress(PlaywrightError):
                nav.final_url = page.url if page.url != "about:blank" else None
        return nav

    @staticmethod
    def _navigation_failure_kind(message: str, recorder: _EventRecorder) -> str:
        events = recorder.proxy.events
        if "ERR_TUNNEL_CONNECTION_FAILED" in message or "ERR_PROXY" in message:
            if events.blocked:
                return "blocked_by_policy"
            if events.unresolved:
                return "dns_failure"
            if events.unreachable:
                return "connection_failed"
        if "ERR_NAME_NOT_RESOLVED" in message:
            return "dns_failure"
        if "ERR_CERT" in message or "SSL" in message:
            return "tls_error"
        if "ERR_CONNECTION" in message or "ERR_ADDRESS" in message:
            return "connection_failed"
        return "browser_error"

    async def _snapshot(self, page: Page) -> dict | None:
        try:
            snapshot = await page.evaluate(_PAGE_SNAPSHOT_JS)
        except PlaywrightError:
            return None
        if not isinstance(snapshot, dict) or not isinstance(snapshot.get("hrefs"), list):
            return None
        snapshot["hrefs"] = [href for href in snapshot["hrefs"] if isinstance(href, str)]
        return snapshot

    async def _screenshot(self, page: Page, page_url: str) -> CheckResult:
        started = _now()
        path = self.output_dir / SCREENSHOT_FILE
        try:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            await page.screenshot(
                path=str(path),
                type="png",
                full_page=False,  # viewport only: bounded size for very long pages
                timeout=_SCREENSHOT_TIMEOUT_MS,
                animations="disabled",
            )
        except (PlaywrightError, OSError) as error:
            message = error.message if isinstance(error, PlaywrightError) else str(error)
            return self._error_check(
                "screenshot", page_url, f"Screenshot failed: {clean_text(message, 200)}", started
            )
        size = path.stat().st_size
        if size > self.limits.max_screenshot_bytes:
            path.unlink(missing_ok=True)
            return self._error_check(
                "screenshot",
                page_url,
                f"Screenshot discarded: {size} bytes exceeds the "
                f"{self.limits.max_screenshot_bytes}-byte limit.",
                started,
            )
        self.artifacts.append(
            ArtifactResult(
                key="screenshot",
                kind="screenshot",
                file_name=SCREENSHOT_FILE,
                content_type="image/png",
                size_bytes=size,
                width=self.limits.viewport_width,
                height=self.limits.viewport_height,
                sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            )
        )
        return CheckResult(
            name=CHECK_NAMES["screenshot"],
            check_type="screenshot",
            status="passed",
            target_url=redact_url(page_url) or page_url,
            summary=f"Captured a {self.limits.viewport_width}×{self.limits.viewport_height} "
            "viewport screenshot.",
            started_at=started,
            finished_at=_now(),
            duration_ms=int((_now() - started).total_seconds() * 1000),
            details={"size_bytes": size},
        )

    @staticmethod
    def _error_check(check_type: str, url: str, summary: str, started: datetime) -> CheckResult:
        finished = _now()
        return CheckResult(
            name=CHECK_NAMES[check_type],
            check_type=check_type,
            status="error",
            target_url=redact_url(url) or url,
            summary=clean_text(summary, 500),
            started_at=started,
            finished_at=finished,
            duration_ms=int((finished - started).total_seconds() * 1000),
        )
