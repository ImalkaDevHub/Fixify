"""Content, accessibility, and performance indicators (pure rules + one real-browser scan)."""

from datetime import UTC, datetime

from app.scanner.checks import (
    SLOW_LOAD_LOW_MS,
    SLOW_LOAD_MEDIUM_MS,
    ContentSnapshot,
    ImageInfo,
    InsecureReference,
    Window,
    check_content,
    content_snapshot,
)
from app.scanner.classify import FindingCollector

PAGE = "https://example.com/page?session=abc"
WINDOW = Window(datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 1, 1, tzinfo=UTC))


def _image(src="https://example.com/a.png", **overrides) -> ImageInfo:
    values = {
        "has_alt": True,
        "decorative": False,
        "complete": True,
        "natural_width": 10,
        "lazy": False,
    }
    return ImageInfo(src=src, **{**values, **overrides})


def _run(snapshot: ContentSnapshot, navigation_ms: int = 300):
    collector = FindingCollector()
    result = check_content(snapshot, navigation_ms, PAGE, collector, WINDOW)
    return result, {f.finding_type: f for f in collector.all()}


def _clean(**overrides) -> ContentSnapshot:
    values = {"h1_count": 1, "meta_description": "About us", "images": [], "insecure": []}
    return ContentSnapshot(**{**values, **overrides})


def test_clean_page_passes():
    result, findings = _run(_clean(images=[_image()]))
    assert result.status == "passed" and findings == {}
    assert result.details["images_checked"] == 1


def test_broken_images_are_confirmed_only_when_loading_finished():
    result, findings = _run(
        _clean(
            images=[
                _image("https://example.com/broken.png", natural_width=0),
                _image("https://cdn.other.net/x.png?token=s3cret", natural_width=0),
                _image("https://example.com/lazy.png", natural_width=0, complete=False, lazy=True),
                _image("data:image/png;base64,AAAA", natural_width=0),
            ]
        )
    )
    broken = [f for f in findings.values() if f.finding_type == "broken_image"]
    # Only one survives in the dict view; check via the result details instead.
    assert result.details["broken_images"] == 2
    assert result.status == "failed"
    assert all("s3cret" not in (f.affected_url or "") for f in broken)


def test_broken_image_severity_depends_on_party():
    collector = FindingCollector()
    check_content(
        _clean(
            images=[
                _image("https://example.com/own.png", natural_width=0),
                _image("https://cdn.other.net/x.png", natural_width=0),
            ]
        ),
        100,
        PAGE,
        collector,
        WINDOW,
    )
    severities = {f.affected_url: f.severity for f in collector.all()}
    assert severities == {
        "https://example.com/own.png": "medium",
        "https://cdn.other.net/x.png": "low",
    }


def test_missing_alt_ignores_decorative_images():
    _, findings = _run(
        _clean(
            images=[
                _image(has_alt=False),
                _image("https://example.com/b.png", has_alt=False),
                _image("https://example.com/deco.png", has_alt=False, decorative=True),
                _image("https://example.com/empty-alt.png", has_alt=True),
            ]
        )
    )
    finding = findings["missing_alt_text"]
    assert finding.severity == "low"
    assert finding.evidence["count"] == 2
    assert len(finding.evidence["examples"]) == 2


def test_headings_and_meta_description():
    _, findings = _run(_clean(h1_count=3, meta_description="   "))
    assert findings["multiple_h1"].severity == "info"
    assert findings["multiple_h1"].evidence["h1_count"] == 3
    assert findings["missing_meta_description"].severity == "info"


def test_info_findings_do_not_fail_the_check():
    result, findings = _run(_clean(meta_description=None))
    assert set(findings) == {"missing_meta_description"}
    assert result.status == "passed"


def test_mixed_content_active_and_passive():
    _, findings = _run(
        _clean(
            insecure=[
                InsecureReference("script", "http://example.com/app.js"),
                InsecureReference("iframe", "http://ads.example.net/frame"),
                InsecureReference("img", "http://example.com/logo.png?key=hunter2"),
            ]
        )
    )
    active, passive = findings["mixed_content_active"], findings["mixed_content_passive"]
    assert (active.severity, active.evidence["count"]) == ("high", 2)
    assert active.evidence["elements"] == ["iframe", "script"]
    assert (passive.severity, passive.evidence["count"]) == ("low", 1)
    assert "hunter2" not in str(passive.evidence)


def test_slow_load_is_suspected_not_confirmed():
    _, fast = _run(_clean(load_ms=SLOW_LOAD_LOW_MS - 1))
    _, slow = _run(_clean(load_ms=SLOW_LOAD_LOW_MS))
    _, very_slow = _run(_clean(load_ms=None), navigation_ms=SLOW_LOAD_MEDIUM_MS + 5)
    assert "slow_page_load" not in fast
    assert slow["slow_page_load"].severity == "low"
    assert slow["slow_page_load"].confidence == "suspected"
    assert very_slow["slow_page_load"].severity == "medium"


def test_snapshot_parsing_rejects_hostile_values():
    snapshot = content_snapshot(
        {
            "h1Count": "lots",
            "metaDescription": ["not", "a", "string"],
            "images": [
                {"src": 5},
                "junk",
                {"src": "https://e.com/x" + "a" * 5000, "naturalWidth": -3, "complete": 1},
            ],
            "insecure": [{"tag": "SCRIPT", "url": "http://e.com/x.js"}, {"url": "http://y"}],
            "timing": {"load": True, "domContentLoaded": 1234.6},
        }
    )
    assert snapshot.h1_count == 0
    assert snapshot.meta_description is None
    assert len(snapshot.images) == 1 and len(snapshot.images[0].src) == 2048
    assert snapshot.images[0].natural_width == 0
    assert snapshot.insecure == [InsecureReference("script", "http://e.com/x.js")]
    assert snapshot.load_ms is None and snapshot.dom_content_loaded_ms == 1234


def test_snapshot_parsing_of_garbage_does_not_crash():
    snapshot = content_snapshot({"images": "x", "insecure": None, "timing": "y"})
    assert snapshot.images == [] and snapshot.insecure == []
