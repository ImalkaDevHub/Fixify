import uuid
from datetime import datetime

from pydantic import BaseModel


class SeverityTotals(BaseModel):
    critical: int = 0
    high: int = 0
    medium: int = 0
    low: int = 0
    info: int = 0


class DailyPoint(BaseModel):
    date: str
    scans: int
    failed_scans: int
    new_findings: int
    resolved_findings: int
    severity: SeverityTotals
    health: int | None


class ProjectHealth(BaseModel):
    project_id: uuid.UUID
    name: str
    health: int | None
    latest_scan_id: uuid.UUID | None
    latest_scan_at: datetime | None
    findings: int


class ScanHistoryItem(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    project_name: str
    status: str
    trigger: str
    created_at: datetime
    duration_ms: int | None
    findings: int
    critical: int
    high: int


class AnalyticsOverview(BaseModel):
    days: int
    project_count: int
    scan_count: int
    finished_scan_count: int
    failed_scan_count: int
    active_scan_count: int
    average_duration_ms: int | None
    current_findings: SeverityTotals
    new_findings: int
    resolved_findings: int
    open_fix_proposals: int
    open_pull_requests: int
    daily: list[DailyPoint]
    projects: list[ProjectHealth]
    recent_scans: list[ScanHistoryItem]
    health_formula: str = (
        "Per scan: 100 - (25 x critical + 10 x high + 4 x medium + 1 x low), minimum 0."
    )
