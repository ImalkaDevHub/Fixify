"""Background jobs, AI analyses, GitHub connections, fixes, pull requests, notifications, and
schedules. Large content (screenshots, whole source files) is never stored here: fixes keep only
bounded snippets plus the Git blob SHA they were made against."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

JsonDocument = JSON().with_variant(JSONB(), "postgresql")

JOB_STATUSES = ("queued", "running", "succeeded", "failed", "cancelled")
JOB_KINDS = ("analyze_finding", "generate_fix", "create_pull_request")
FIX_STATUSES = (
    "pending_review",
    "approved",
    "rejected",
    "applied",
    "failed_validation",
    "superseded",
)
VALIDATION_STATUSES = ("passed", "failed", "not_available")
CONFIDENCE_LEVELS = ("low", "medium", "high")
COMPLEXITY_LEVELS = ("trivial", "small", "medium", "large")
REVIEW_ACTIONS = ("comment", "approve", "reject", "reopen")
PR_STATUSES = ("creating", "open", "closed", "merged", "failed")
SCHEDULE_FREQUENCIES = ("daily", "weekly", "custom")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(value) for value in values)})"


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


def _fk(target: str, ondelete: str = "CASCADE", nullable: bool = False) -> Mapped[Any]:
    return mapped_column(
        UUID(as_uuid=True), ForeignKey(target, ondelete=ondelete), nullable=nullable
    )


def _created() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


def _updated() -> Mapped[datetime]:
    return mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class BackgroundJob(Base):
    """AI and GitHub work, processed by the worker with the same claim/heartbeat/retry rules as
    scans. Status is the source of truth; the frontend shows it as-is."""

    __tablename__ = "background_jobs"
    __table_args__ = (
        CheckConstraint(_in("status", JOB_STATUSES), name="ck_background_jobs_status"),
        CheckConstraint(_in("kind", JOB_KINDS), name="ck_background_jobs_kind"),
        Index("ix_background_jobs_status_run_after", "status", "run_after"),
        Index("ix_background_jobs_owner_created", "owner_id", "created_at"),
        Index("ix_background_jobs_kind_subject", "kind", "subject_id"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="queued")
    owner_id: Mapped[uuid.UUID] = _fk("users.id")
    project_id: Mapped[uuid.UUID] = _fk("projects.id")
    # The object the job acts on (finding for analysis/fix, fix proposal for pull requests).
    subject_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JsonDocument, nullable=False, default=dict)
    # ID of the object the job produced (analysis, fix proposal, pull request).
    result_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    run_after: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()


class AIAnalysis(Base):
    __tablename__ = "ai_analyses"
    __table_args__ = (
        CheckConstraint(_in("confidence", CONFIDENCE_LEVELS), name="ck_ai_analyses_confidence"),
        CheckConstraint(_in("fix_complexity", COMPLEXITY_LEVELS), name="ck_ai_analyses_complexity"),
        Index("ix_ai_analyses_finding_created", "finding_id", "created_at"),
        Index("ix_ai_analyses_project_created", "project_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    project_id: Mapped[uuid.UUID] = _fk("projects.id")
    finding_id: Mapped[uuid.UUID] = _fk("findings.id")
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    technical_explanation: Mapped[str] = mapped_column(Text, nullable=False)
    root_cause: Mapped[str] = mapped_column(Text, nullable=False)
    user_impact: Mapped[str] = mapped_column(Text, nullable=False)
    why_it_matters: Mapped[str] = mapped_column(Text, nullable=False)
    recommended_solution: Mapped[str] = mapped_column(Text, nullable=False)
    fix_complexity: Mapped[str] = mapped_column(String(16), nullable=False)
    confidence: Mapped[str] = mapped_column(String(16), nullable=False)
    # [{"path": str, "reason": str}] - only paths that exist in the connected repository.
    suggested_locations: Mapped[list[Any]] = mapped_column(
        JsonDocument, nullable=False, default=list
    )
    evidence_refs: Mapped[list[Any]] = mapped_column(JsonDocument, nullable=False, default=list)
    related_finding_ids: Mapped[list[Any]] = mapped_column(
        JsonDocument, nullable=False, default=list
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = _created()


class GitHubConnection(Base):
    __tablename__ = "github_connections"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    github_user_id: Mapped[str] = mapped_column(String(32), nullable=False)
    login: Mapped[str] = mapped_column(String(100), nullable=False)
    avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    scopes: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    # Fernet ciphertext (TOKEN_ENCRYPTION_KEY). The plaintext token never leaves the backend.
    token_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    last_validated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()


class FixProposal(Base):
    __tablename__ = "fix_proposals"
    __table_args__ = (
        CheckConstraint(_in("status", FIX_STATUSES), name="ck_fix_proposals_status"),
        CheckConstraint(
            _in("validation_status", VALIDATION_STATUSES), name="ck_fix_proposals_validation"
        ),
        CheckConstraint(_in("confidence", CONFIDENCE_LEVELS), name="ck_fix_proposals_confidence"),
        Index("ix_fix_proposals_project_created", "project_id", "created_at"),
        Index("ix_fix_proposals_finding_created", "finding_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    project_id: Mapped[uuid.UUID] = _fk("projects.id")
    finding_id: Mapped[uuid.UUID] = _fk("findings.id")
    analysis_id: Mapped[uuid.UUID | None] = _fk("ai_analyses.id", "SET NULL", nullable=True)
    parent_id: Mapped[uuid.UUID | None] = _fk("fix_proposals.id", "SET NULL", nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending_review")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    repo_full_name: Mapped[str] = mapped_column(String(100), nullable=False)
    base_branch: Mapped[str] = mapped_column(String(255), nullable=False)
    base_commit_sha: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    impact: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[str] = mapped_column(String(16), nullable=False)
    validation_status: Mapped[str] = mapped_column(String(16), nullable=False)
    validation_messages: Mapped[list[Any]] = mapped_column(
        JsonDocument, nullable=False, default=list
    )
    # [{"path", "blob_sha", "language", "original", "proposed", "start_line"}], bounded.
    changes: Mapped[list[Any]] = mapped_column(JsonDocument, nullable=False, default=list)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    created_by_id: Mapped[uuid.UUID | None] = _fk("users.id", "SET NULL", nullable=True)
    reviewed_by_id: Mapped[uuid.UUID | None] = _fk("users.id", "SET NULL", nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()


class FixReview(Base):
    __tablename__ = "fix_reviews"
    __table_args__ = (
        CheckConstraint(_in("action", REVIEW_ACTIONS), name="ck_fix_reviews_action"),
        Index("ix_fix_reviews_fix_created", "fix_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    fix_id: Mapped[uuid.UUID] = _fk("fix_proposals.id")
    user_id: Mapped[uuid.UUID | None] = _fk("users.id", "SET NULL", nullable=True)
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = _created()


class PullRequest(Base):
    __tablename__ = "pull_requests"
    __table_args__ = (
        CheckConstraint(_in("status", PR_STATUSES), name="ck_pull_requests_status"),
        Index("ix_pull_requests_project_created", "project_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    fix_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("fix_proposals.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    project_id: Mapped[uuid.UUID] = _fk("projects.id")
    repo_full_name: Mapped[str] = mapped_column(String(100), nullable=False)
    branch_name: Mapped[str] = mapped_column(String(255), nullable=False)
    base_branch: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="creating")
    commit_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)
    number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (
        Index("ix_notifications_user_created", "user_id", "created_at"),
        Index("ix_notifications_user_unread", "user_id", "read_at"),
        UniqueConstraint("user_id", "dedupe_key", name="uq_notifications_user_dedupe"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = _fk("users.id")
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(String(1000), nullable=False, default="")
    link: Mapped[str | None] = mapped_column(String(500), nullable=True)
    project_id: Mapped[uuid.UUID | None] = _fk("projects.id", nullable=True)
    # Makes notifications idempotent when a job or scan result is processed twice.
    dedupe_key: Mapped[str | None] = mapped_column(String(200), nullable=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = _created()


class UserPreferences(Base):
    __tablename__ = "user_preferences"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    # {notification kind: bool}; kinds missing from the map are enabled.
    notifications: Mapped[dict[str, Any]] = mapped_column(
        JsonDocument, nullable=False, default=dict
    )
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()


class ScanSchedule(Base):
    __tablename__ = "scan_schedules"
    __table_args__ = (
        CheckConstraint(_in("frequency", SCHEDULE_FREQUENCIES), name="ck_scan_schedules_frequency"),
        Index("ix_scan_schedules_due", "enabled", "next_run_at"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    frequency: Mapped[str] = mapped_column(String(16), nullable=False)
    hour_utc: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    weekday: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 0 = Monday
    interval_hours: Mapped[int | None] = mapped_column(Integer, nullable=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_run_id: Mapped[uuid.UUID | None] = _fk("test_runs.id", "SET NULL", nullable=True)
    last_outcome: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()
