"""Create scan runs, check results, findings, and artifacts.

Revision ID: 0002_scans
Revises: 0001_projects
Create Date: 2026-10-22
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0002_scans"
down_revision: str | None = "0001_projects"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    ]


def _counter(name: str) -> sa.Column:
    return sa.Column(name, sa.Integer(), nullable=False)


def upgrade() -> None:
    op.create_table(
        "test_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("target_url", sa.String(length=2048), nullable=False),
        sa.Column("final_url", sa.String(length=2048), nullable=True),
        sa.Column("max_links", sa.Integer(), nullable=False),
        _counter("attempts"),
        sa.Column("failure_reason", sa.String(length=500), nullable=True),
        _counter("checks_total"),
        _counter("checks_passed"),
        _counter("checks_failed"),
        _counter("checks_errored"),
        _counter("checks_skipped"),
        _counter("findings_count"),
        _counter("critical_count"),
        _counter("high_count"),
        _counter("medium_count"),
        _counter("low_count"),
        _counter("info_count"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'completed', 'completed_with_errors', "
            "'failed', 'cancelled')",
            name="ck_test_runs_status",
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_test_runs_project_created", "test_runs", ["project_id", "created_at"])
    op.create_index("ix_test_runs_status_created", "test_runs", ["status", "created_at"])

    op.create_table(
        "scan_artifacts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("test_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("content_type", sa.String(length=64), nullable=False),
        sa.Column("storage_key", sa.String(length=200), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["test_run_id"], ["test_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_scan_artifacts_run", "scan_artifacts", ["test_run_id"])

    op.create_table(
        "test_case_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("test_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("check_type", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("target_url", sa.String(length=2048), nullable=False),
        sa.Column("summary", sa.String(length=500), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        *_timestamps(),
        sa.CheckConstraint(
            "status IN ('passed', 'failed', 'skipped', 'error')",
            name="ck_test_case_results_status",
        ),
        sa.ForeignKeyConstraint(["test_run_id"], ["test_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("test_run_id", "check_type", name="uq_test_case_results_run_check"),
    )

    op.create_table(
        "findings",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("test_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("check_type", sa.String(length=50), nullable=False),
        sa.Column("finding_type", sa.String(length=50), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("confidence", sa.String(length=16), nullable=False),
        sa.Column("affected_url", sa.String(length=2048), nullable=True),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("artifact_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("first_detected_at", sa.DateTime(timezone=True), nullable=False),
        *_timestamps(),
        sa.CheckConstraint(
            "severity IN ('critical', 'high', 'medium', 'low', 'info')",
            name="ck_findings_severity",
        ),
        sa.CheckConstraint(
            "confidence IN ('confirmed', 'suspected')", name="ck_findings_confidence"
        ),
        sa.ForeignKeyConstraint(["artifact_id"], ["scan_artifacts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["test_run_id"], ["test_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("test_run_id", "fingerprint", name="uq_findings_run_fingerprint"),
    )
    op.create_index("ix_findings_run_severity", "findings", ["test_run_id", "severity"])
    op.create_index("ix_findings_project_created", "findings", ["project_id", "created_at"])
    op.create_index(
        "ix_findings_project_fingerprint", "findings", ["project_id", "fingerprint"]
    )


def downgrade() -> None:
    op.drop_index("ix_findings_project_fingerprint", table_name="findings")
    op.drop_index("ix_findings_project_created", table_name="findings")
    op.drop_index("ix_findings_run_severity", table_name="findings")
    op.drop_table("findings")
    op.drop_table("test_case_results")
    op.drop_index("ix_scan_artifacts_run", table_name="scan_artifacts")
    op.drop_table("scan_artifacts")
    op.drop_index("ix_test_runs_status_created", table_name="test_runs")
    op.drop_index("ix_test_runs_project_created", table_name="test_runs")
    op.drop_table("test_runs")
