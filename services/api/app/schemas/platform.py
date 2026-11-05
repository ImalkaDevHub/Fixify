import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

JobStatus = Literal["queued", "running", "succeeded", "failed", "cancelled"]
FixStatus = Literal[
    "pending_review", "approved", "rejected", "applied", "failed_validation", "superseded"
]


class JobRead(BaseModel):
    id: uuid.UUID
    kind: str
    status: JobStatus
    project_id: uuid.UUID
    subject_id: uuid.UUID
    result_id: uuid.UUID | None
    error: str | None
    attempts: int
    max_attempts: int
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class AIStatus(BaseModel):
    available: bool
    provider: str | None
    model: str | None


class AnalysisRead(BaseModel):
    id: uuid.UUID
    finding_id: uuid.UUID
    project_id: uuid.UUID
    summary: str
    technical_explanation: str
    root_cause: str
    user_impact: str
    why_it_matters: str
    recommended_solution: str
    fix_complexity: str
    confidence: str
    suggested_locations: list[dict[str, Any]]
    evidence_refs: list[str]
    related_finding_ids: list[str]
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class FindingAIState(BaseModel):
    ai: AIStatus
    analysis: AnalysisRead | None
    active_job: JobRead | None
    last_job: JobRead | None


# --- GitHub -----------------------------------------------------------------------------------


class GitHubStatus(BaseModel):
    configured: bool
    connected: bool
    status: str | None = None
    login: str | None = None
    avatar_url: str | None = None
    scopes: list[str] = Field(default_factory=list)
    connected_at: datetime | None = None


class GitHubAuthorize(BaseModel):
    authorize_url: str


class RepositoryRead(BaseModel):
    id: str
    full_name: str
    private: bool
    default_branch: str
    description: str | None
    html_url: str | None
    can_push: bool
    updated_at: str | None


class RepositoryConnect(BaseModel):
    model_config = ConfigDict(extra="forbid")

    repo_full_name: str = Field(min_length=3, max_length=201)
    branch: str | None = Field(default=None, max_length=255)


class RepositoryFile(BaseModel):
    path: str
    size: int


class RepositoryTree(BaseModel):
    repo_full_name: str
    branch: str
    commit_sha: str
    truncated: bool
    files: list[RepositoryFile]


# --- Fixes ------------------------------------------------------------------------------------


class FixRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    file_paths: list[str] = Field(default_factory=list, max_length=10)
    instructions: str | None = Field(default=None, max_length=2_000)


class RegenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    instructions: str | None = Field(default=None, max_length=2_000)
    file_paths: list[str] = Field(default_factory=list, max_length=10)


class ReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["comment", "approve", "reject", "reopen"]
    comment: str | None = Field(default=None, max_length=5_000)


class FileChangeRead(BaseModel):
    path: str
    language: str
    start_line: int
    original: str
    proposed: str
    edits: list[dict[str, str]]


class ReviewRead(BaseModel):
    id: uuid.UUID
    action: str
    comment: str | None
    user_id: uuid.UUID | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PullRequestRead(BaseModel):
    id: uuid.UUID
    status: str
    repo_full_name: str
    branch_name: str
    base_branch: str
    commit_sha: str | None
    number: int | None
    url: str | None
    error: str | None
    last_synced_at: datetime | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class FixSummary(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    finding_id: uuid.UUID
    status: FixStatus
    version: int
    title: str
    confidence: str
    validation_status: str
    repo_full_name: str
    base_branch: str
    files: list[str]
    created_at: datetime
    updated_at: datetime


class FixDetail(FixSummary):
    analysis_id: uuid.UUID | None
    parent_id: uuid.UUID | None
    base_commit_sha: str
    explanation: str
    impact: str
    validation_messages: list[str]
    changes: list[FileChangeRead]
    provider: str
    model: str
    reviewed_at: datetime | None
    reviews: list[ReviewRead]
    pull_request: PullRequestRead | None
    finding_title: str | None = None
    finding_severity: str | None = None


# --- Notifications and schedules ---------------------------------------------------------------


class NotificationRead(BaseModel):
    id: uuid.UUID
    kind: str
    title: str
    body: str
    link: str | None
    project_id: uuid.UUID | None
    read_at: datetime | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class NotificationList(BaseModel):
    items: list[NotificationRead]
    unread_count: int


class NotificationPreference(BaseModel):
    kind: str
    label: str
    enabled: bool


class PreferencesUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    notifications: dict[str, bool]


class ScheduleUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    frequency: Literal["daily", "weekly", "custom"] = "daily"
    hour_utc: int = Field(default=3, ge=0, le=23)
    weekday: int | None = Field(default=None, ge=0, le=6)
    interval_hours: int | None = Field(default=None, ge=1, le=720)


class ScheduleRead(BaseModel):
    project_id: uuid.UUID
    enabled: bool
    frequency: str
    hour_utc: int
    weekday: int | None
    interval_hours: int | None
    next_run_at: datetime | None
    last_run_at: datetime | None
    last_run_id: uuid.UUID | None
    last_outcome: str | None

    model_config = ConfigDict(from_attributes=True)
