"""Pure analysis functions that turn observed browser events into check results and findings.

The engine records raw events from Playwright; these functions classify them. Keeping them free
of browser objects makes every rule unit-testable.
"""

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from urllib.parse import urlsplit

from app.scanner.classify import (
    FindingCollector,
    broken_link_severity,
    document_status_severity,
    is_first_party,
    network_failure_severity,
    resource_status_severity,
    strip_query,
)
from app.scanner.contract import CheckResult, CheckStatus
from app.scanner.links import LinkCheck
from app.scanner.sanitize import MAX_STACK_CHARS, clean_text, redact_url

# Chromium logs every failed sub-resource as a console error ("Failed to load resource: ...").
# Those are reported by the network checks with better context, so the console check ignores
# them. This is the only console exclusion rule.
_CONSOLE_DUPLICATE_PREFIX = "Failed to load resource:"
# Cancelled requests (navigation away, aborted fetches, media range requests) are not bugs.
_IGNORED_FAILURES = ("net::ERR_ABORTED", "NS_BINDING_ABORTED", "NS_ERROR_ABORT")
_PROXY_NETWORK_REASONS = {
    "dns_failure": "The host name could not be resolved.",
    "connection_failed": "The server could not be reached.",
}


@dataclass(frozen=True)
class ConsoleEvent:
    text: str
    url: str | None = None
    line: int | None = None
    column: int | None = None


@dataclass(frozen=True)
class PageErrorEvent:
    message: str
    name: str | None = None
    stack: str | None = None


@dataclass(frozen=True)
class RequestFailureEvent:
    url: str
    method: str
    resource_type: str
    failure: str
    frame_url: str | None = None
    proxy_reason: str | None = None
    at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class ResponseErrorEvent:
    url: str
    status: int
    method: str
    resource_type: str
    frame_url: str | None = None
    proxy_reason: str | None = None


@dataclass
class NavigationOutcome:
    requested_url: str
    final_url: str | None = None
    status: int | None = None
    error_kind: str | None = None  # timeout | browser_error | blocked_by_policy | dns_failure ...
    error_message: str | None = None
    duration_ms: int = 0
    redirect_chain: list[str] = field(default_factory=list)

    @property
    def document_loaded(self) -> bool:
        """A document from the website was received (even an error page with status >= 400)."""
        return self.status is not None and self.error_kind is None


@dataclass(frozen=True)
class PageSnapshot:
    title: str | None
    h1_count: int
    has_viewport_meta: bool
    icon_declared: bool
    favicon_status: int | None = None  # /favicon.ico status when no icon is declared


@dataclass(frozen=True)
class Window:
    started_at: datetime
    finished_at: datetime

    @property
    def duration_ms(self) -> int:
        return max(0, int((self.finished_at - self.started_at).total_seconds() * 1000))


def _result(
    *,
    name: str,
    check_type: str,
    status: CheckStatus,
    target_url: str,
    summary: str,
    window: Window,
    details: dict[str, object] | None = None,
) -> CheckResult:
    return CheckResult(
        name=name,
        check_type=check_type,
        status=status,
        target_url=redact_url(target_url) or target_url,
        summary=clean_text(summary, 500),
        started_at=window.started_at,
        finished_at=window.finished_at,
        duration_ms=window.duration_ms,
        details=details or {},
    )


def _status_from(collector: FindingCollector, check_type: str) -> CheckStatus:
    findings = collector.for_check(check_type)
    return "failed" if any(finding.severity != "info" for finding in findings) else "passed"


def skipped(name: str, check_type: str, target_url: str, reason: str, at: datetime) -> CheckResult:
    return _result(
        name=name,
        check_type=check_type,
        status="skipped",
        target_url=target_url,
        summary=reason,
        window=Window(at, at),
    )


def check_navigation(
    nav: NavigationOutcome, collector: FindingCollector, window: Window
) -> CheckResult:
    check_type = "page_navigation"
    details = {
        "final_url": redact_url(nav.final_url),
        "http_status": nav.status,
        "navigation_ms": nav.duration_ms,
        "redirects": [redact_url(url) for url in nav.redirect_chain][:10],
    }
    url = nav.requested_url
    if nav.error_kind == "blocked_by_policy":
        collector.add(
            key=(url,),
            check_type=check_type,
            finding_type="navigation_blocked",
            title="Navigation blocked by the scanner safety policy",
            description=(
                "The website, or a redirect it issued, pointed to a destination the scanner "
                "may not visit (for example a private or local network address)."
            ),
            severity="high",
            affected_url=nav.final_url or url,
            evidence={"reason": nav.error_message},
        )
        summary = "Navigation was blocked by the scanner safety policy."
    elif nav.error_kind == "timeout":
        collector.add(
            key=(url,),
            check_type=check_type,
            finding_type="navigation_timeout",
            title="Page did not finish loading in time",
            description=(
                f"The page did not fire its load event within the navigation timeout "
                f"({nav.duration_ms // 1000} s)."
            ),
            severity="critical",
            affected_url=url,
            evidence={"timeout_ms": nav.duration_ms},
        )
        summary = "Navigation timed out."
    elif nav.error_kind is not None:
        explanation = _PROXY_NETWORK_REASONS.get(nav.error_kind, "The browser could not load it.")
        collector.add(
            key=(url, nav.error_kind),
            check_type=check_type,
            finding_type="navigation_error",
            title="Website could not be loaded",
            description=f"Navigation failed before any page was received. {explanation}",
            severity="critical",
            affected_url=url,
            evidence={"error": clean_text(nav.error_message or nav.error_kind, 500)},
        )
        summary = f"Navigation failed: {clean_text(nav.error_kind, 80)}."
    elif nav.status is not None and nav.status >= 400:
        collector.add(
            key=(strip_query(nav.final_url or url), nav.status),
            check_type=check_type,
            finding_type="http_error_document",
            title=f"Page responded with HTTP {nav.status}",
            description=(
                "The main document returned an error status. The browser rendered a page, but "
                "the server reported that the request failed."
            ),
            severity=document_status_severity(nav.status),
            affected_url=nav.final_url or url,
            http_status=nav.status,
        )
        summary = f"Page loaded with HTTP {nav.status}."
    else:
        summary = f"Page loaded with HTTP {nav.status} in {nav.duration_ms} ms."
    return _result(
        name="Page navigation",
        check_type=check_type,
        status=_status_from(collector, check_type),
        target_url=url,
        summary=summary,
        window=window,
        details=details,
    )


def check_console(
    events: Iterable[ConsoleEvent], target_url: str, collector: FindingCollector, window: Window
) -> CheckResult:
    check_type = "console_errors"
    ignored = 0
    for event in events:
        if event.text.startswith(_CONSOLE_DUPLICATE_PREFIX):
            ignored += 1
            continue
        message = clean_text(event.text)
        collector.add(
            key=(message, strip_query(event.url or "")),
            check_type=check_type,
            finding_type="console_error",
            title="JavaScript console error",
            description=message,
            severity="medium",
            affected_url=event.url or target_url,
            evidence={
                "message": message,
                "source_url": redact_url(event.url),
                "line": event.line,
                "column": event.column,
            },
        )
    count = len(collector.for_check(check_type))
    return _result(
        name="JavaScript console errors",
        check_type=check_type,
        status=_status_from(collector, check_type),
        target_url=target_url,
        summary=f"{count} distinct console error(s)." if count else "No console errors.",
        window=window,
        details={"ignored_network_duplicates": ignored},
    )


def check_exceptions(
    events: Iterable[PageErrorEvent], target_url: str, collector: FindingCollector, window: Window
) -> CheckResult:
    check_type = "uncaught_exceptions"
    for event in events:
        message = clean_text(event.message)
        collector.add(
            key=(event.name, message),
            check_type=check_type,
            finding_type="uncaught_exception",
            title=f"Uncaught {clean_text(event.name or 'JavaScript error', 60)}",
            description=message,
            severity="high",
            affected_url=target_url,
            evidence={
                "name": clean_text(event.name or "", 100) or None,
                "message": message,
                "stack": clean_text(event.stack, MAX_STACK_CHARS) if event.stack else None,
            },
        )
    count = len(collector.for_check(check_type))
    return _result(
        name="Uncaught JavaScript exceptions",
        check_type=check_type,
        status=_status_from(collector, check_type),
        target_url=target_url,
        summary=f"{count} distinct uncaught exception(s)." if count else "No uncaught exceptions.",
        window=window,
    )


def _blocked_request(collector: FindingCollector, check_type: str, url: str) -> None:
    host = urlsplit(url).netloc
    collector.add(
        key=(host,),
        check_type=check_type,
        finding_type="request_blocked",
        title="Request blocked by the scanner safety policy",
        description=(
            "The page tried to load a resource from a destination the scanner may not reach, "
            "such as a private or local address. This is reported for information; it is not "
            "necessarily a bug in the website."
        ),
        severity="info",
        affected_url=url,
        evidence={"host": host},
    )


def check_failed_requests(
    events: Iterable[RequestFailureEvent],
    site_url: str,
    collector: FindingCollector,
    window: Window,
) -> CheckResult:
    check_type = "failed_requests"
    cancelled = 0
    for event in events:
        if event.proxy_reason == "blocked_by_policy":
            _blocked_request(collector, check_type, event.url)
            continue
        if any(marker in event.failure for marker in _IGNORED_FAILURES):
            cancelled += 1
            continue
        first_party = is_first_party(event.url, site_url)
        reason = _PROXY_NETWORK_REASONS.get(event.proxy_reason or "", clean_text(event.failure))
        collector.add(
            key=(strip_query(event.url), event.proxy_reason or event.failure),
            check_type=check_type,
            finding_type="network_failure",
            title=f"Failed to load {event.resource_type} resource",
            description=f"The request failed at the network level: {reason}",
            severity=network_failure_severity(event.resource_type, first_party),
            affected_url=event.url,
            evidence={
                "method": event.method,
                "resource_type": event.resource_type,
                "failure": clean_text(event.proxy_reason or event.failure, 200),
                "page_url": redact_url(event.frame_url),
                "first_party": first_party,
                "observed_at": event.at.isoformat(),
            },
        )
    count = len(collector.for_check(check_type))
    return _result(
        name="Failed network requests",
        check_type=check_type,
        status=_status_from(collector, check_type),
        target_url=site_url,
        summary=f"{count} distinct failed request(s)." if count else "No failed requests.",
        window=window,
        details={"ignored_cancellations": cancelled},
    )


def check_http_errors(
    events: Iterable[ResponseErrorEvent],
    site_url: str,
    document_url: str | None,
    collector: FindingCollector,
    window: Window,
) -> CheckResult:
    check_type = "http_errors"
    for event in events:
        if document_url and event.url == document_url and event.resource_type == "document":
            continue  # the main document is reported by the navigation check
        if event.proxy_reason == "blocked_by_policy":
            _blocked_request(collector, check_type, event.url)
            continue
        if event.proxy_reason is not None:
            continue  # proxy-generated 502s are network failures, not website responses
        first_party = is_first_party(event.url, site_url)
        collector.add(
            key=(strip_query(event.url), event.status),
            check_type=check_type,
            finding_type="http_error_resource",
            title=f"{event.resource_type.capitalize()} request returned HTTP {event.status}",
            description=(
                f"A {'first' if first_party else 'third'}-party {event.resource_type} request "
                f"received an HTTP {event.status} response."
            ),
            severity=resource_status_severity(event.status, event.resource_type, first_party),
            affected_url=event.url,
            http_status=event.status,
            evidence={
                "method": event.method,
                "resource_type": event.resource_type,
                "page_url": redact_url(event.frame_url),
                "first_party": first_party,
            },
        )
    count = len(collector.for_check(check_type))
    return _result(
        name="HTTP error responses",
        check_type=check_type,
        status=_status_from(collector, check_type),
        target_url=site_url,
        summary=f"{count} distinct error response(s)." if count else "No error responses.",
        window=window,
    )


def check_page_basics(
    snapshot: PageSnapshot, page_url: str, collector: FindingCollector, window: Window
) -> CheckResult:
    check_type = "page_basics"
    if not (snapshot.title or "").strip():
        collector.add(
            key=(strip_query(page_url),),
            check_type=check_type,
            finding_type="missing_title",
            title="Page title is missing or empty",
            description="The document has no non-empty <title>, which browsers and search "
            "engines use to identify the page.",
            severity="low",
            affected_url=page_url,
        )
    if snapshot.h1_count == 0:
        collector.add(
            key=(strip_query(page_url),),
            check_type=check_type,
            finding_type="missing_h1",
            title="No primary heading (<h1>) found",
            description="The rendered page contains no <h1> element.",
            severity="info",
            affected_url=page_url,
        )
    if not snapshot.has_viewport_meta:
        collector.add(
            key=(strip_query(page_url),),
            check_type=check_type,
            finding_type="missing_viewport_meta",
            title="No responsive viewport meta tag",
            description="Without <meta name=\"viewport\">, mobile browsers render the page at "
            "desktop width.",
            severity="low",
            affected_url=page_url,
        )
    if not snapshot.icon_declared and snapshot.favicon_status in (404, 410):
        collector.add(
            key=(strip_query(page_url),),
            check_type=check_type,
            finding_type="missing_favicon",
            title="No favicon found",
            description="The page declares no icon and /favicon.ico returned "
            f"HTTP {snapshot.favicon_status}.",
            severity="info",
            affected_url=page_url,
            http_status=snapshot.favicon_status,
        )
    findings = collector.for_check(check_type)
    return _result(
        name="Basic page checks",
        check_type=check_type,
        status=_status_from(collector, check_type),
        target_url=page_url,
        summary=(
            f"{len(findings)} basic page issue(s)."
            if findings
            else "Title, heading, viewport, and favicon look fine."
        ),
        window=window,
        details={
            "title": clean_text(snapshot.title or "", 200),
            "h1_count": snapshot.h1_count,
            "has_viewport_meta": snapshot.has_viewport_meta,
            "icon_declared": snapshot.icon_declared,
            "note": "Basic indicators only; this is not an accessibility or SEO audit.",
        },
    )


def check_links(
    results: list[LinkCheck],
    links_found: int,
    site_url: str,
    collector: FindingCollector,
    window: Window,
) -> CheckResult:
    check_type = "broken_links"
    counts = {"ok": 0, "broken": 0, "suspected": 0, "inconclusive": 0, "blocked": 0}
    inconclusive: list[dict[str, object]] = []
    for result in results:
        counts[result.verdict] += 1
        if result.verdict in ("broken", "suspected"):
            first_party = is_first_party(result.url, site_url)
            confirmed = result.verdict == "broken"
            collector.add(
                key=(result.url,),
                check_type=check_type,
                finding_type="broken_link" if confirmed else "possibly_broken_link",
                title="Broken link" if confirmed else "Link may be broken",
                description=(
                    f"The link returned HTTP {result.status}."
                    if confirmed
                    else "The link could not be loaded "
                    f"({result.reason or f'HTTP {result.status}'}). This may be temporary."
                ),
                severity=broken_link_severity(first_party) if confirmed else "low",
                confidence="confirmed" if confirmed else "suspected",
                affected_url=result.url,
                http_status=result.status,
                evidence={
                    "final_url": redact_url(result.final_url),
                    "reason": result.reason,
                    "first_party": first_party,
                },
            )
        elif result.verdict in ("inconclusive", "blocked"):
            inconclusive.append(
                {
                    "url": redact_url(result.url),
                    "verdict": result.verdict,
                    "status": result.status,
                    "reason": result.reason,
                }
            )
    return _result(
        name="Broken links",
        check_type=check_type,
        status=_status_from(collector, check_type),
        target_url=site_url,
        summary=(
            f"Checked {len(results)} of {links_found} link(s): {counts['broken']} broken, "
            f"{counts['suspected']} suspected, {counts['inconclusive']} inconclusive, "
            f"{counts['blocked']} blocked by policy."
        ),
        window=window,
        details={
            "links_found": links_found,
            "links_checked": len(results),
            "counts": counts,
            "not_confirmed": inconclusive[:50],
        },
    )
