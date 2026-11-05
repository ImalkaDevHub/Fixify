"""Website ownership verification fields on projects.

Revision ID: 0005_site_verification
Revises: 0004_platform
Create Date: 2026-11-05
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0005_site_verification"
down_revision: str | None = "0004_platform"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("projects", sa.Column("verification_token", sa.String(length=64), nullable=True))
    op.add_column("projects", sa.Column("verified_host", sa.String(length=255), nullable=True))
    op.add_column("projects", sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("projects", sa.Column("verification_method", sa.String(length=16), nullable=True))


def downgrade() -> None:
    op.drop_column("projects", "verification_method")
    op.drop_column("projects", "verified_at")
    op.drop_column("projects", "verified_host")
    op.drop_column("projects", "verification_token")
