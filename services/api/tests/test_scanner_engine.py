"""Scanner tests against a local controlled website with a real headless Chromium.

Skipped when the Playwright Chromium build is not installed (`python -m playwright install
chromium`). No test reaches the internet: the fixture site runs on 127.0.0.1 and is the only
host on the scanner's development allowlist.
"""

import asyncio
from pathlib import Path
from urllib.parse import urlsplit

import httpx
import pytest

from app.scanner.contract import PolicyConfig, ScanJob, ScanLimits, ScanResult
from app.scanner.egress_proxy import PROXY_HEADER, EgressProxy
from app.scanner.engine import ScanEngine
from app.scanner.links import LinkChecker
from app.scanner.url_policy import UrlPolicy
from tests.fixtures.scan_site import serve_site


def _chromium_installed() -> bool:
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as playwright:
            return Path(playwright.chromium.executable_path).exists()
    except Exception:  # noqa: BLE001
        return False


requires_chromium = pytest.mark.skipif(
    not _chromium_installed(), reason="Playwright Chromium is not installed"
)


@pytest.fixture(scope="module")
def site():
    with serve_site() as (base, blocked):
        yield base, blocked


def _policy(base: str) -> PolicyConfig:
    return PolicyConfig(unsafe_allowed_hosts=frozenset({urlsplit(base).netloc}))


def _scan(site, path: str, tmp_path: Path, **limits: int) -> ScanResult:
    base, _blocked = site
    job = ScanJob(
        run_id="test",
        target_url=base + path,
        output_dir=str(tmp_path),
        limits=ScanLimits(
            navigation_timeout_seconds=limits.pop("navigation_timeout_seconds", 10),
            max_scan_duration_seconds=60,
            link_timeout_seconds=3,
            **limits,
        ),
        policy=_policy(base),
    )
    return asyncio.run(ScanEngine(job).run())


def _types(result: ScanResult) -> dict[str, str]:
    return {finding.finding_type: finding.severity for finding in result.findings}


def _check(result: ScanResult, check_type: str) -> str:
    return next(check.status for check in result.checks if check.check_type == check_type)


# --- Egress proxy: the enforcement point for every connection -----------------------------


def test_proxy_forwards_allowed_and_blocks_other_loopback_ports(site):
    base, blocked = site

    async def run() -> tuple[httpx.Response, httpx.Response]:
        proxy = EgressProxy(UrlPolicy(_policy(base)))
        await proxy.start()
        try:
            async with httpx.AsyncClient(proxy=proxy.url, trust_env=False) as client:
                return await client.get(base + "/ok"), await client.get(blocked + "/admin")
        finally:
            await proxy.close()

    allowed, refused = asyncio.run(run())
    assert allowed.status_code == 200 and PROXY_HEADER not in allowed.headers
    assert refused.status_code == 403
    assert refused.headers[PROXY_HEADER] == "blocked_by_policy"


def test_redirects_are_checked_at_every_hop(site):
    base, _blocked = site

    async def run():
        proxy = EgressProxy(UrlPolicy(_policy(base)))
        await proxy.start()
        try:
            async with LinkChecker(proxy.url, timeout_seconds=3, concurrency=2) as checker:
                return await checker.check(base + "/redirect-internal")
        finally:
            await proxy.close()

    result = asyncio.run(run())
    assert result.verdict == "blocked"


def test_proxy_blocks_https_connect_to_private_address():
    async def run() -> str:
        proxy = EgressProxy(UrlPolicy(PolicyConfig()))
        await proxy.start()
        try:
            reader, writer = await asyncio.open_connection("127.0.0.1", proxy.port)
            writer.write(b"CONNECT 169.254.169.254:443 HTTP/1.1\r\nHost: x\r\n\r\n")
            await writer.drain()
            line = await reader.readline()
            writer.close()
            return line.decode()
        finally:
            await proxy.close()

    assert " 403 " in asyncio.run(run())


# --- Real browser scans of the fixture pages ----------------------------------------------


@requires_chromium
def test_successful_page_with_screenshot(site, tmp_path):
    result = _scan(site, "/ok", tmp_path)
    assert result.outcome == "completed"
    assert result.findings == []
    assert {check.status for check in result.checks} == {"passed"}
    screenshot = result.artifacts[0]
    assert screenshot.kind == "screenshot" and screenshot.size_bytes > 0
    assert (tmp_path / screenshot.file_name).read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


@requires_chromium
@pytest.mark.parametrize(("path", "status"), [("/missing", 404), ("/server-error", 500)])
def test_error_status_pages_are_not_successful(site, tmp_path, path, status):
    result = _scan(site, path, tmp_path)
    assert result.outcome == "completed"  # the scan worked; the website has a bug
    assert _check(result, "page_navigation") == "failed"
    finding = next(f for f in result.findings if f.finding_type == "http_error_document")
    assert finding.http_status == status and finding.severity == "high"


@requires_chromium
def test_console_errors_are_deduplicated_and_warnings_ignored(site, tmp_path):
    result = _scan(site, "/console-error", tmp_path)
    console = [f for f in result.findings if f.finding_type == "console_error"]
    assert len(console) == 1
    assert console[0].evidence["occurrences"] == 2
    assert "fixture console failure" in console[0].description


@requires_chromium
def test_uncaught_exception(site, tmp_path):
    result = _scan(site, "/exception", tmp_path)
    finding = next(f for f in result.findings if f.finding_type == "uncaught_exception")
    assert "fixture uncaught failure" in finding.description
    assert finding.severity == "high"


@requires_chromium
def test_failed_and_blocked_sub_resources(site, tmp_path):
    result = _scan(site, "/failed-script", tmp_path)
    by_type = {}
    for finding in result.findings:
        by_type.setdefault(finding.finding_type, []).append(finding)
    assert by_type["http_error_resource"][0].http_status == 404
    assert by_type["http_error_resource"][0].severity == "high"  # first-party script
    assert by_type["network_failure"][0].evidence["failure"] == "dns_failure"
    assert by_type["request_blocked"][0].severity == "info"


@requires_chromium
def test_broken_links(site, tmp_path):
    result = _scan(site, "/broken-links", tmp_path)
    confirmed = {f.affected_url.rsplit("/", 1)[-1] for f in result.findings
                 if f.finding_type == "broken_link"}
    suspected = {f.affected_url for f in result.findings
                 if f.finding_type == "possibly_broken_link"}
    assert confirmed == {"gone", "redirect-to-gone"}
    assert any(url.endswith("/flaky") for url in suspected)
    details = next(c for c in result.checks if c.check_type == "broken_links").details
    assert details["counts"]["blocked"] == 1  # the internal link was never requested
    assert details["counts"]["ok"] >= 1


@requires_chromium
def test_missing_title_and_basics(site, tmp_path):
    result = _scan(site, "/no-title", tmp_path)
    types = _types(result)
    assert types["missing_title"] == "low"
    assert "missing_h1" in types and "missing_viewport_meta" in types


@requires_chromium
def test_navigation_timeout(site, tmp_path):
    result = _scan(site, "/slow", tmp_path, navigation_timeout_seconds=2)
    assert result.outcome == "completed"
    assert _types(result) == {"navigation_timeout": "critical"}
    assert _check(result, "screenshot") == "skipped"


@requires_chromium
def test_redirect_to_internal_address_is_blocked_in_the_browser(site, tmp_path):
    result = _scan(site, "/redirect-internal", tmp_path)
    assert _types(result) == {"navigation_blocked": "high"}


def test_blocked_target_fails_without_launching_a_browser(tmp_path):
    job = ScanJob(
        run_id="x",
        target_url="http://169.254.169.254/latest/meta-data/",
        output_dir=str(tmp_path),
        limits=ScanLimits(),
        policy=PolicyConfig(),
    )
    result = asyncio.run(ScanEngine(job).run())
    assert result.outcome == "failed"
    assert "safety policy" in (result.failure_reason or "")
    assert result.findings == []


@requires_chromium
def test_worker_runs_the_real_scanner_subprocess(site, tmp_path):
    """The executor path used in production: separate process, minimal env, JSON over pipes."""
    from app.worker.executor import run_scanner

    base, _blocked = site
    job = ScanJob(
        run_id="subprocess",
        target_url=base + "/ok",
        output_dir=str(tmp_path),
        limits=ScanLimits(max_scan_duration_seconds=60, link_timeout_seconds=3),
        policy=_policy(base),
    )
    result = asyncio.run(run_scanner(job))
    assert result.outcome == "completed"
    screenshot = next(check for check in result.checks if check.check_type == "screenshot")
    assert "×" in screenshot.summary  # non-ASCII text survives the pipe on every platform
    assert (tmp_path / "screenshot.png").exists()
