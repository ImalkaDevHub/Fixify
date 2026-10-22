"""Deterministic severity rules, fingerprints, and per-scan finding deduplication."""

import hashlib
from urllib.parse import urlsplit

from app.scanner.contract import Confidence, FindingResult, Severity
from app.scanner.sanitize import bounded_evidence, clean_text, redact_url

_CRITICAL_RESOURCES = frozenset({"script", "stylesheet"})
_DATA_RESOURCES = frozenset({"xhr", "fetch"})


def fingerprint(*parts: object) -> str:
    """Stable identity for "the same issue", used for deduplication and scan comparison."""
    material = "\x1f".join(str(part) for part in parts)
    return hashlib.sha256(material.encode()).hexdigest()


def strip_query(url: str) -> str:
    """URL without query or fragment, so cache-busting parameters do not split one issue."""
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}{parts.path}"


def is_first_party(url: str, site_url: str) -> bool:
    host = (urlsplit(url).hostname or "").lower()
    site = (urlsplit(site_url).hostname or "").lower()
    if not host or not site:
        return False
    site_root = site.removeprefix("www.")
    return host == site or host == site_root or host.endswith("." + site_root)


def document_status_severity(status: int) -> Severity:
    if status >= 500 or status in (404, 410):
        return "high"
    return "medium"


def resource_status_severity(status: int, resource_type: str, first_party: bool) -> Severity:
    if not first_party:
        # Third-party failures (analytics, ads, widgets) are worth knowing but rarely urgent.
        return "medium" if resource_type in _CRITICAL_RESOURCES and status >= 500 else "low"
    if resource_type in _CRITICAL_RESOURCES:
        return "high"
    if resource_type in _DATA_RESOURCES:
        if status >= 500:
            return "high"
        # 401/403 from an API call is often expected for an anonymous visitor.
        return "low" if status in (401, 403) else "medium"
    if resource_type == "document":  # iframes and other sub-documents
        return "medium"
    return "low"


def network_failure_severity(resource_type: str, first_party: bool) -> Severity:
    if not first_party:
        return "low"
    if resource_type in _CRITICAL_RESOURCES:
        return "high"
    if resource_type in _DATA_RESOURCES or resource_type == "document":
        return "medium"
    return "low"


def broken_link_severity(first_party: bool) -> Severity:
    return "medium" if first_party else "low"


class FindingCollector:
    """Collects findings, merging repeats of the same fingerprint into one finding."""

    def __init__(self) -> None:
        self._findings: dict[str, FindingResult] = {}

    def add(
        self,
        *,
        key: tuple[object, ...],
        check_type: str,
        finding_type: str,
        title: str,
        description: str,
        severity: Severity,
        confidence: Confidence = "confirmed",
        affected_url: str | None = None,
        http_status: int | None = None,
        evidence: dict[str, object] | None = None,
        artifact_key: str | None = None,
    ) -> FindingResult:
        identity = fingerprint(finding_type, *key)
        existing = self._findings.get(identity)
        if existing is not None:
            existing.evidence["occurrences"] = int(existing.evidence.get("occurrences", 1)) + 1
            return existing
        finding = FindingResult(
            check_type=check_type,
            finding_type=finding_type,
            title=clean_text(title, 200),
            description=clean_text(description, 2_000),
            severity=severity,
            confidence=confidence,
            affected_url=redact_url(affected_url),
            http_status=http_status,
            evidence=bounded_evidence({"occurrences": 1, **(evidence or {})}),
            fingerprint=identity,
            artifact_key=artifact_key,
        )
        self._findings[identity] = finding
        return finding

    def for_check(self, check_type: str) -> list[FindingResult]:
        return [finding for finding in self._findings.values() if finding.check_type == check_type]

    def all(self) -> list[FindingResult]:
        return list(self._findings.values())
