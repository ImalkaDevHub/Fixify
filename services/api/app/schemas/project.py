import re
import uuid
from datetime import datetime

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, field_validator

from app.schemas.scan import LatestScan

_REPOSITORY_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_CONTROL_CHARACTERS = re.compile(r"[\x00-\x1f\x7f]")


def _reject_control_characters(value: str) -> str:
    # PostgreSQL cannot store NUL; other control characters never belong in these fields.
    if _CONTROL_CHARACTERS.search(value):
        raise ValueError("Control characters are not allowed.")
    return value


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    website_url: AnyHttpUrl = Field(max_length=2048)
    description: str | None = Field(default=None, max_length=500)
    scan_max_links: int | None = Field(default=None, ge=0, le=200)
    repo_full_name: str | None = Field(default=None, max_length=100)
    default_branch: str | None = Field(default=None, max_length=255)

    @field_validator("name")
    @classmethod
    def strip_project_name(cls, value: str) -> str:
        value = _reject_control_characters(value.strip())
        if not value:
            raise ValueError("Project name cannot be empty.")
        return value

    @field_validator("description")
    @classmethod
    def clean_description(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if any((ord(char) < 32 and char not in "\n\t") or ord(char) == 127 for char in value):
            raise ValueError("Control characters are not allowed.")
        return value or None

    @field_validator("repo_full_name")
    @classmethod
    def validate_repository(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        normalized = value.strip()
        owner, _, repository = normalized.partition("/")
        if not _REPOSITORY_PATTERN.fullmatch(normalized) or {owner, repository} & {".", ".."}:
            raise ValueError("Repository must use the owner/repository format.")
        return normalized

    @field_validator("default_branch")
    @classmethod
    def normalize_branch(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = _reject_control_characters(value.strip())
        return normalized or None


class ProjectUpdate(ProjectCreate):
    """Partial update: only the fields sent are changed. Blank optionals clear the value."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=100)  # type: ignore[assignment]
    website_url: AnyHttpUrl | None = Field(default=None, max_length=2048)  # type: ignore[assignment]

    @field_validator("name")
    @classmethod
    def strip_project_name(cls, value: str | None) -> str | None:  # type: ignore[override]
        if value is None:
            return None
        return ProjectCreate.strip_project_name(value)


class ProjectRead(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None = None
    scan_max_links: int | None = None
    website_url: str
    repo_full_name: str | None
    github_repo_id: str | None
    default_branch: str | None
    verified_host: str | None = None
    verified_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ProjectWithLatestScan(ProjectRead):
    latest_scan: LatestScan | None = None
