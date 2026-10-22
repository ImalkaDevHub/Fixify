"""Unit tests for the scanner's deterministic rules: no browser, no network."""

import uuid
from datetime import UTC, datetime

import pytest

from app.core.artifacts import (
    ArtifactPathError,
    cleanup_expired,
    resolve_artifact_path,
    storage_key,
    store_file,
)
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
from app.scanner.classify import (
    FindingCollector,
    document_status_severity,
    is_first_party,
    resource_status_severity,
)
from app.scanner.contract import CheckResult, ScanResult
from app.scanner.links import LinkCheck, classify_status, normalize_link, select_links
from app.scanner.sanitize import MAX_EVIDENCE_BYTES, bounded_evidence, clean_text, redact_url

SITE = "https://shop.example.com/"
NOW = datetime(2026, 1, 1, tzinfo=UTC)
WINDOW = Window(NOW, NOW)


def test_severity_rules():
    assert document_status_severity(500) == "high"
    assert document_status_severity(404) == "high"
    assert document_status_severity(403) == "medium"
    assert resource_status_severity(404, "script", first_party=True) == "high"
    assert resource_status_severity(404, "script", first_party=False) == "low"
    assert resource_status_severity(500, "fetch", first_party=True) == "high"
    assert resource_status_severity(401, "fetch", first_party=True) == "low"
    assert resource_status_severity(404, "image", first_party=True) == "low"
    # A third-party analytics 404 must never be critical.
    assert resource_status_severity(404, "xhr", first_party=False) == "low"


def test_first_party_detection():
    assert is_first_party("https://cdn.shop.example.com/a.js", "https://www.shop.example.com/")
    assert is_first_party("https://shop.example.com/a.js", SITE)
    assert not is_first_party("https://analytics.other.net/t.js", SITE)
    assert not is_first_party("https://evilshop.example.com.attacker.net/", SITE)


def test_collector_deduplicates_and_counts_occurrences():
    collector = FindingCollector()
    for _ in range(3):
        checks.check_console([ConsoleEvent("boom", "https://shop.example.com/app.js")], SITE,
                             collector, WINDOW)
    findings = collector.all()
    assert len(findings) == 1
    assert findings[0].evidence["occurrences"] == 3


def test_console_ignores_resource_load_duplicates_and_is_medium():
    collector = FindingCollector()
    result = checks.check_console(
        [
            ConsoleEvent("Failed to load resource: the server responded with a status of 404"),
            ConsoleEvent("Uncaught ReferenceError: x is not defined"),
        ],
        SITE,
        collector,
        WINDOW,
    )
    assert result.status == "failed"
    assert result.details["ignored_network_duplicates"] == 1
    assert [finding.severity for finding in collector.all()] == ["medium"]


def test_exceptions_are_high_and_stack_is_bounded():
    collector = FindingCollector()
    checks.check_exceptions(
        [PageErrorEvent("bad", "TypeError", "at x\n" * 5_000)], SITE, collector, WINDOW
    )
    finding = collector.all()[0]
    assert finding.severity == "high"
    assert len(finding.evidence["stack"]) <= 4_000


def test_cancelled_requests_are_not_findings():
    collector = FindingCollector()
    result = checks.check_failed_requests(
        [
            RequestFailureEvent(SITE + "a.js", "GET", "script", "net::ERR_ABORTED"),
            RequestFailureEvent(SITE + "b.js", "GET", "script", "net::ERR_CONNECTION_RESET"),
        ],
        SITE,
        collector,
        WINDOW,
    )
    assert result.details["ignored_cancellations"] == 1
    assert [(f.finding_type, f.severity) for f in collector.all()] == [("network_failure", "high")]


def test_policy_blocks_are_info_not_bugs():
    collector = FindingCollector()
    result = checks.check_failed_requests(
        [
            RequestFailureEvent(
                "http://10.0.0.1/x.png", "GET", "image", "x", proxy_reason="blocked_by_policy"
            )
        ],
        SITE,
        collector,
        WINDOW,
    )
    assert result.status == "passed"
    assert collector.all()[0].severity == "info"


def test_http_errors_skip_main_document_and_proxy_responses():
    collector = FindingCollector()
    checks.check_http_errors(
        [
            ResponseErrorEvent(SITE, 500, "GET", "document"),
            ResponseErrorEvent(SITE + "x.js", 502, "GET", "script", proxy_reason="dns_failure"),
            ResponseErrorEvent(SITE + "app.css?v=1", 404, "GET", "stylesheet"),
            ResponseErrorEvent(SITE + "app.css?v=2", 404, "GET", "stylesheet"),
        ],
        SITE,
        SITE,
        collector,
        WINDOW,
    )
    findings = collector.all()
    assert len(findings) == 1  # cache-busting query strings do not split one issue
    assert findings[0].http_status == 404


@pytest.mark.parametrize(
    ("nav", "finding_type", "severity"),
    [
        (NavigationOutcome(SITE, status=200), None, None),
        (NavigationOutcome(SITE, status=503), "http_error_document", "high"),
        (NavigationOutcome(SITE, error_kind="timeout"), "navigation_timeout", "critical"),
        (NavigationOutcome(SITE, error_kind="dns_failure"), "navigation_error", "critical"),
        (
            NavigationOutcome(SITE, error_kind="blocked_by_policy"),
            "navigation_blocked",
            "high",
        ),
    ],
)
def test_navigation_outcomes(nav, finding_type, severity):
    collector = FindingCollector()
    result = checks.check_navigation(nav, collector, WINDOW)
    if finding_type is None:
        assert result.status == "passed" and not collector.all()
    else:
        assert result.status == "failed"
        assert (collector.all()[0].finding_type, collector.all()[0].severity) == (
            finding_type,
            severity,
        )


def test_an_error_page_is_not_a_successful_document_load():
    assert NavigationOutcome(SITE, status=404).document_loaded  # page received, error reported
    assert not NavigationOutcome(SITE, error_kind="timeout").document_loaded


def test_page_basics():
    collector = FindingCollector()
    result = checks.check_page_basics(
        PageSnapshot(title="  ", h1_count=0, has_viewport_meta=True, icon_declared=False,
                     favicon_status=404),
        SITE,
        collector,
        WINDOW,
    )
    types = {finding.finding_type for finding in collector.all()}
    assert types == {"missing_title", "missing_h1", "missing_favicon"}
    assert result.status == "failed"


def test_link_normalization_and_selection():
    assert normalize_link("mailto:a@b.c", SITE) is None
    assert normalize_link("tel:+1", SITE) is None
    assert normalize_link("javascript:void(0)", SITE) is None
    assert normalize_link("#top", SITE) is None
    assert normalize_link("https://u:p@x.example.com/", SITE) is None
    assert normalize_link("/a#b", SITE) == "https://shop.example.com/a"
    assert normalize_link("HTTPS://Shop.Example.com:443/a", SITE) == "https://shop.example.com/a"
    links, found = select_links(["/a", "/a#x", "/b", "/c", "mailto:x"], SITE, limit=2)
    assert links == ["https://shop.example.com/a", "https://shop.example.com/b"]
    assert found == 3


def test_link_status_classification():
    assert classify_status(200) == "ok"
    assert classify_status(404) == "broken"
    assert classify_status(410) == "broken"
    assert classify_status(503) == "suspected"
    for status in (401, 403, 429, 999):
        assert classify_status(status) == "inconclusive"


def test_only_confirmed_links_are_confirmed_findings():
    collector = FindingCollector()
    checks.check_links(
        [
            LinkCheck(SITE + "gone", "broken", status=404),
            LinkCheck(SITE + "flaky", "suspected", status=503),
            LinkCheck(SITE + "slow", "inconclusive", reason="timeout"),
            LinkCheck("http://10.0.0.1/", "blocked", reason="blocked_by_policy"),
        ],
        4,
        SITE,
        collector,
        WINDOW,
    )
    by_type = {finding.finding_type: finding for finding in collector.all()}
    assert set(by_type) == {"broken_link", "possibly_broken_link"}
    assert by_type["broken_link"].confidence == "confirmed"
    assert by_type["possibly_broken_link"].confidence == "suspected"


def test_redaction():
    assert redact_url("https://u:p@example.com/a?token=abc&page=2#frag") == (
        "https://example.com/a?token=%5Bredacted%5D&page=2"
    )
    assert redact_url("data:text/html,<script>alert(1)</script>") == "data:[omitted]"
    assert redact_url("http://[bad") == "[invalid URL]"
    assert "[redacted]" in clean_text("Authorization: Bearer abcdefghijklmnop")
    assert "\x00" not in clean_text("a\x00b")
    assert len(clean_text("x" * 5_000)) == 1_000


def test_evidence_is_bounded():
    evidence = bounded_evidence({"items": ["y" * 2_000] * 100, "note": "z" * 50_000})
    import json

    assert len(json.dumps(evidence).encode()) <= MAX_EVIDENCE_BYTES
    assert evidence["truncated"] is True


def test_scan_result_round_trips_as_json():
    check = CheckResult(
        name="n", check_type="t", status="passed", target_url=SITE, summary="s",
        started_at=NOW, finished_at=NOW, duration_ms=0,
    )
    result = ScanResult(requested_url=SITE, started_at=NOW, finished_at=NOW,
                        outcome="completed", checks=[check])
    assert ScanResult.model_validate_json(result.model_dump_json()) == result
    assert (result.passed_count, result.failed_count, result.error_count) == (1, 0, 0)


@pytest.mark.parametrize(
    "key",
    [
        "../secret.png",
        "/etc/passwd",
        "..\\..\\x.png",
        f"{uuid.uuid4()}/../../x.png",
        f"{uuid.uuid4()}/{uuid.uuid4()}.exe",
        f"{uuid.uuid4()}/{uuid.uuid4()}",
        f"{uuid.uuid4()}/{uuid.uuid4()}/x.png",
        "C:/Windows/win.ini",
        "",
    ],
)
def test_artifact_keys_cannot_escape_the_store(tmp_path, key):
    with pytest.raises(ArtifactPathError):
        resolve_artifact_path(tmp_path, key)


def test_artifact_store_enforces_size_limit(tmp_path):
    source = tmp_path / "shot.png"
    source.write_bytes(b"x" * 2_000)
    key = storage_key(uuid.uuid4(), uuid.uuid4())
    with pytest.raises(ArtifactPathError):
        store_file(tmp_path / "store", source, key, max_bytes=1_000)
    assert store_file(tmp_path / "store", source, key, max_bytes=5_000) == 2_000
    assert resolve_artifact_path(tmp_path / "store", key).read_bytes() == source.read_bytes()


def test_retention_cleanup_only_touches_run_directories(tmp_path):
    keep, orphan = uuid.uuid4(), uuid.uuid4()
    (tmp_path / str(keep)).mkdir()
    (tmp_path / str(orphan)).mkdir()
    (tmp_path / "unrelated").mkdir()
    removed = cleanup_expired(tmp_path, retention_days=30, known_run_ids={str(keep)})
    assert removed == 1
    assert (tmp_path / str(keep)).exists()
    assert (tmp_path / "unrelated").exists()
    assert not (tmp_path / str(orphan)).exists()
