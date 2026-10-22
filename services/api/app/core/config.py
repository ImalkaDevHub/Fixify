from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

API_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    app_name: str = "Fixify API"
    app_env: str = "development"
    database_url: str = (
        "postgresql+psycopg://fixify:change-me-locally@localhost:5432/fixify"
    )
    database_connect_timeout_seconds: int = 5
    redis_url: str = "redis://localhost:6379/0"
    redis_required: bool = True
    api_cors_origins: str = "http://localhost:3000"

    # Scan queue. "redis" pushes run IDs to a Redis list; "database" lets the worker poll
    # PostgreSQL only (for native development without Redis). PostgreSQL is always the
    # source of truth for run state.
    queue_backend: Literal["redis", "database"] = "redis"
    scan_queue_name: str = "fixify:scan-runs"

    # Artifacts (screenshots) live outside the web root and are served only through the API.
    artifact_dir: Path = API_ROOT / ".artifacts"
    artifact_retention_days: int = Field(default=14, ge=1, le=365)
    artifact_max_bytes: int = Field(default=5_000_000, ge=10_000, le=20_000_000)

    # Scanner limits. The bounds are hard caps: configuration cannot switch the limits off.
    scanner_navigation_timeout_seconds: int = Field(default=30, ge=5, le=120)
    scanner_max_scan_duration_seconds: int = Field(default=180, ge=30, le=900)
    scanner_max_links: int = Field(default=25, ge=0, le=200)
    scanner_link_concurrency: int = Field(default=4, ge=1, le=10)
    scanner_link_timeout_seconds: int = Field(default=8, ge=2, le=30)
    scanner_viewport_width: int = Field(default=1280, ge=320, le=1920)
    scanner_viewport_height: int = Field(default=800, ge=320, le=1440)
    scanner_allowed_ports: str = "80,443,8080,8443"
    # Comma-separated host:port pairs that bypass the private-network block. Development and
    # test fixtures ONLY (for example "127.0.0.1:4100"). Never set this in a shared deployment.
    scanner_unsafe_allowed_hosts: str = ""
    scanner_max_queued_scans: int = Field(default=20, ge=1, le=500)

    worker_concurrency: int = Field(default=1, ge=1, le=4)
    worker_poll_interval_seconds: int = Field(default=5, ge=1, le=60)
    scan_max_attempts: int = Field(default=2, ge=1, le=5)

    model_config = SettingsConfigDict(
        env_file=("../../.env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.api_cors_origins.split(",") if origin.strip()]

    @property
    def redis_needed(self) -> bool:
        return self.redis_required or self.queue_backend == "redis"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
