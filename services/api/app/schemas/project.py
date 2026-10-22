import re
import uuid
from datetime import datetime

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, field_validator

_REPOSITORY_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    website_url: AnyHttpUrl = Field(max_length=2048)
    repo_full_name: str | None = Field(default=None, max_length=100)
    default_branch: str | None = Field(default=None, max_length=255)

    @field_validator("name")
    @classmethod
    def strip_project_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Project name cannot be empty.")
        return value

    @field_validator("repo_full_name")
    @classmethod
    def validate_repository(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        normalized = value.strip()
        if not _REPOSITORY_PATTERN.fullmatch(normalized):
            raise ValueError("Repository must use the owner/repository format.")
        return normalized

    @field_validator("default_branch")
    @classmethod
    def normalize_branch(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class ProjectRead(BaseModel):
    id: uuid.UUID
    name: str
    website_url: str
    repo_full_name: str | None
    github_repo_id: str | None
    default_branch: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
