import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field

RunStatus = Literal[
    "queued", "running", "completed", "completed_with_errors", "failed", "cancelled"
]
SeverityName = Literal["critical", "high", "medium", "low", "info"]


class ScanCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_url: AnyHttpUrl | None = Field(
        default=None,
        max_length=2048,
        description="Defaults to the project's website URL. Must pass the scanner URL policy.",
    )
    max_links: int | None = Field(
        default=None,
        ge=0,
        le=200,
        description="Links to check; capped by the server's SCANNER_MAX_LINKS.",
    )


class ScanQueued(BaseModel):
    id: uuid.UUID
    status: RunStatus
    project_id: uuid.UUID
    target_url: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SeverityCounts(BaseModel):
    critical: int
    high: int
    medium: int
    low: int
    info: int


class RunSummary(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    status: RunStatus
    target_url: str
    final_url: str | None
    failure_reason: str | None
    attempts: int
    max_links: int
    checks_total: int
    checks_passed: int
    checks_failed: int
    checks_errored: int
    checks_skipped: int
    findings_count: int
    severity_counts: SeverityCounts
    started_at: datetime | None
    finished_at: datetime | None
    duration_ms: int | None
    created_at: datetime
    updated_at: datetime


class CheckRead(BaseModel):
    id: uuid.UUID
    name: str
    check_type: str
    status: Literal["passed", "failed", "skipped", "error"]
    target_url: str
    summary: str
    started_at: datetime
    finished_at: datetime
    duration_ms: int
    details: dict[str, Any]

    model_config = ConfigDict(from_attributes=True)


class ArtifactRead(BaseModel):
    id: uuid.UUID
    kind: str
    content_type: str
    size_bytes: int
    width: int | None
    height: int | None
    created_at: datetime
    url: str = Field(description="API path that serves the artifact.")


class RunDetail(RunSummary):
    checks: list[CheckRead]
    artifacts: list[ArtifactRead]


class FindingRead(BaseModel):
    id: uuid.UUID
    test_run_id: uuid.UUID
    project_id: uuid.UUID
    check_type: str
    finding_type: str
    title: str
    description: str
    severity: SeverityName
    confidence: Literal["confirmed", "suspected"]
    affected_url: str | None
    http_status: int | None
    fingerprint: str
    artifact_id: uuid.UUID | None
    first_detected_at: datetime
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class FindingDetail(FindingRead):
    evidence: dict[str, Any]
    artifact: ArtifactRead | None


class ComparisonFinding(BaseModel):
    fingerprint: str
    title: str
    severity: SeverityName
    affected_url: str | None
    finding_id: uuid.UUID


class RunComparison(BaseModel):
    run_id: uuid.UUID
    previous_run_id: uuid.UUID | None
    new: list[ComparisonFinding]
    resolved: list[ComparisonFinding]
    unchanged_count: int


class LatestScan(BaseModel):
    id: uuid.UUID
    status: RunStatus
    created_at: datetime
    finished_at: datetime | None
    findings_count: int


class DashboardSummary(BaseModel):
    project_count: int
    scan_count: int
    active_scan_count: int
    latest_findings_count: int = Field(
        description="Findings in each project's most recent finished scan, summed."
    )
