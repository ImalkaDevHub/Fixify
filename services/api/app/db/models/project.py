import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Project(Base):
    __tablename__ = "projects"
    __table_args__ = (
        Index("ix_projects_created_at", "created_at"),
        Index("ix_projects_repo_full_name", "repo_full_name"),
        Index("ix_projects_owner_created", "owner_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # NULL only for projects created before authentication existed. Such projects are visible
    # to nobody until `python -m app.cli assign-orphans` gives them an owner.
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Links to check per scan; None = server default (SCANNER_MAX_LINKS), always capped by it.
    scan_max_links: Mapped[int | None] = mapped_column(Integer, nullable=True)
    website_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    repo_full_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    github_repo_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    default_branch: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Website ownership verification (meta tag or /.well-known file). Bound to the hostname that
    # was verified: changing the website to another host makes the project unverified again.
    verification_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    verified_host: Mapped[str | None] = mapped_column(String(255), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verification_method: Mapped[str | None] = mapped_column(String(16), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
