"""Typed contract between the worker and the isolated scanner process.

The worker writes a ScanJob as JSON to the scanner's stdin and reads a ScanResult from its
stdout. Nothing in this package imports application settings, so the scanner process never
loads database or Redis credentials.
"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

CheckStatus = Literal["passed", "failed", "skipped", "error"]
Severity = Literal["critical", "high", "medium", "low", "info"]
Confidence = Literal["confirmed", "suspected"]
ScanOutcome = Literal["completed", "completed_with_errors", "failed"]

SEVERITY_ORDER: tuple[Severity, ...] = ("critical", "high", "medium", "low", "info")


class PolicyConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    allowed_ports: frozenset[int] = frozenset({80, 443, 8080, 8443})
    # "host:port" entries that may resolve to private addresses. Development fixtures only.
    unsafe_allowed_hosts: frozenset[str] = frozenset()
    dns_timeout_seconds: float = 5.0


class ScanLimits(BaseModel):
    model_config = ConfigDict(frozen=True)

    navigation_timeout_seconds: int = 30
    max_scan_duration_seconds: int = 180
    max_links: int = 25
    link_concurrency: int = 4
    link_timeout_seconds: int = 8
    viewport_width: int = 1280
    viewport_height: int = 800
    max_screenshot_bytes: int = 5_000_000


class ScanJob(BaseModel):
    run_id: str
    target_url: str
    output_dir: str
    limits: ScanLimits
    policy: PolicyConfig


class CheckResult(BaseModel):
    name: str
    check_type: str
    status: CheckStatus
    target_url: str
    summary: str
    started_at: datetime
    finished_at: datetime
    duration_ms: int
    details: dict[str, Any] = Field(default_factory=dict)


class FindingResult(BaseModel):
    check_type: str
    finding_type: str
    title: str
    description: str
    severity: Severity
    confidence: Confidence
    affected_url: str | None = None
    http_status: int | None = None
    evidence: dict[str, Any] = Field(default_factory=dict)
    fingerprint: str
    # Key of an artifact in ScanResult.artifacts this finding refers to, e.g. "screenshot".
    artifact_key: str | None = None


class ArtifactResult(BaseModel):
    key: str
    kind: Literal["screenshot"]
    file_name: str
    content_type: Literal["image/png"]
    size_bytes: int
    width: int | None = None
    height: int | None = None
    sha256: str


class ScanResult(BaseModel):
    requested_url: str
    final_url: str | None = None
    started_at: datetime
    finished_at: datetime
    outcome: ScanOutcome
    checks: list[CheckResult] = Field(default_factory=list)
    findings: list[FindingResult] = Field(default_factory=list)
    artifacts: list[ArtifactResult] = Field(default_factory=list)
    failure_reason: str | None = None

    @property
    def passed_count(self) -> int:
        return sum(check.status == "passed" for check in self.checks)

    @property
    def failed_count(self) -> int:
        return sum(check.status == "failed" for check in self.checks)

    @property
    def error_count(self) -> int:
        return sum(check.status == "error" for check in self.checks)

    @property
    def skipped_count(self) -> int:
        return sum(check.status == "skipped" for check in self.checks)
