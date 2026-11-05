import os
import secrets
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

API_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    app_name: str = "Fixify API"
    app_env: str = "development"
    database_url: str = (
        "postgresql+psycopg://fixify:change-me-locally@127.0.0.1:5432/fixify"
    )
    database_connect_timeout_seconds: int = 5
    redis_url: str = "redis://127.0.0.1:6379/0"
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

    # --- Authentication -------------------------------------------------------------------
    # Signs access tokens and derives CSRF tokens. Required (32+ characters) in production; in
    # development an empty value is replaced by a random per-process key (sessions then end
    # when the API restarts).
    secret_key: SecretStr = SecretStr("")
    access_token_ttl_minutes: int = Field(default=15, ge=1, le=60)
    refresh_token_ttl_days: int = Field(default=30, ge=1, le=90)
    # None = Secure cookies only in production. Browsers refuse Secure cookies over plain HTTP.
    cookie_secure: bool | None = None
    # Public URL of the web app: used in email links and accepted as a request Origin.
    public_app_url: str = "http://localhost:3000"
    require_email_verification: bool = True
    email_verification_ttl_hours: int = Field(default=48, ge=1, le=168)
    password_reset_ttl_minutes: int = Field(default=30, ge=5, le=240)
    # Argon2id cost. Defaults follow the argon2-cffi recommendation (64 MiB, 3 passes).
    password_hash_memory_kib: int = Field(default=65_536, ge=1_024, le=1_048_576)
    password_hash_time_cost: int = Field(default=3, ge=1, le=10)
    # Fixed-window limits for login, registration and token endpoints.
    auth_rate_limit_per_ip: int = Field(default=30, ge=1, le=10_000)
    auth_rate_limit_per_account: int = Field(default=10, ge=1, le=1_000)
    auth_rate_limit_window_seconds: int = Field(default=900, ge=60, le=86_400)

    # --- Email ------------------------------------------------------------------------------
    # "console" logs messages (development only), "smtp" sends them, "disabled" drops them.
    email_backend: Literal["console", "smtp", "disabled"] = "console"
    email_from: str = "Fixify <no-reply@localhost>"
    smtp_host: str = ""
    smtp_port: int = Field(default=587, ge=1, le=65_535)
    smtp_username: str = ""
    smtp_password: SecretStr = SecretStr("")
    smtp_starttls: bool = True
    smtp_timeout_seconds: int = Field(default=10, ge=1, le=60)

    # --- Per-user limits --------------------------------------------------------------------
    max_projects_per_user: int = Field(default=50, ge=1, le=10_000)
    max_active_scans_per_user: int = Field(default=3, ge=1, le=100)
    # Users must prove control of a website (meta tag or /.well-known file) before scanning it.
    # None = required in production only.
    require_site_verification: bool | None = None

    # --- AI analysis and fix generation ---------------------------------------------------
    # "none" switches AI off; the rest of Fixify keeps working and the UI says AI is unavailable.
    ai_provider: Literal["anthropic", "none"] = "anthropic"
    anthropic_api_key: SecretStr = SecretStr("")
    # Any Claude model ID. For a low-cost setup use e.g. AI_MODEL=claude-haiku-5-5, AI_EFFORT=low.
    ai_model: str = "claude-opus-5-5"
    ai_effort: Literal["low", "medium", "high", "xhigh", "max"] = "medium"
    ai_timeout_seconds: int = Field(default=120, ge=10, le=600)
    ai_max_retries: int = Field(default=2, ge=0, le=5)
    ai_max_output_tokens: int = Field(default=16_000, ge=1_024, le=32_000)
    # Server-side refusal fallback (only sent to models that support it).
    ai_refusal_fallback: bool = True
    ai_jobs_per_user_per_hour: int = Field(default=30, ge=1, le=1_000)

    # --- GitHub integration ---------------------------------------------------------------
    github_client_id: str = ""
    github_client_secret: SecretStr = SecretStr("")
    # "repo" is GitHub's narrowest OAuth-App scope that can push branches to private
    # repositories; "public_repo" limits Fixify to public repositories.
    github_oauth_scopes: str = "repo"
    github_api_url: str = "https://api.github.com"
    github_web_url: str = "https://github.com"
    github_timeout_seconds: int = Field(default=20, ge=5, le=60)
    github_max_file_bytes: int = Field(default=150_000, ge=1_000, le=1_000_000)
    github_max_files_per_fix: int = Field(default=5, ge=1, le=10)
    github_max_context_bytes: int = Field(default=200_000, ge=10_000, le=1_000_000)
    # Fernet key(s), comma-separated, newest first, for GitHub tokens at rest. Generate with
    # python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    token_encryption_key: SecretStr = SecretStr("")

    # --- Background jobs and scheduling -----------------------------------------------------
    job_max_attempts: int = Field(default=3, ge=1, le=10)
    job_concurrency: int = Field(default=2, ge=1, le=8)
    scheduler_interval_seconds: int = Field(default=30, ge=5, le=600)
    min_schedule_interval_hours: int = Field(default=6, ge=1, le=168)

    @property
    def ai_configured(self) -> bool:
        return self.ai_provider == "anthropic" and bool(
            self.anthropic_api_key.get_secret_value().strip()
        )

    @property
    def github_configured(self) -> bool:
        return bool(
            self.github_client_id
            and self.github_client_secret.get_secret_value()
            and self.token_encryption_key.get_secret_value()
        )

    model_config = SettingsConfigDict(
        # FIXIFY_IGNORE_ENV_FILE=1 (set by the test suite) keeps a developer's .env, and the
        # database it points to, out of automated tests.
        env_file=None if os.environ.get("FIXIFY_IGNORE_ENV_FILE") else ("../../.env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @model_validator(mode="after")
    def _check_security_settings(self) -> "Settings":
        if self.is_production:
            problems = []
            if len(self.secret_key.get_secret_value()) < 32:
                problems.append("SECRET_KEY must be at least 32 characters")
            if self.email_backend == "console":
                problems.append("EMAIL_BACKEND=console is for development only")
            if self.cookie_secure is False:
                problems.append("COOKIE_SECURE cannot be false in production")
            if self.scanner_unsafe_allowed_hosts.strip():
                problems.append("SCANNER_UNSAFE_ALLOWED_HOSTS must be empty in production")
            if problems:
                raise ValueError("Unsafe production configuration: " + "; ".join(problems))
        elif not self.secret_key.get_secret_value():
            self.secret_key = SecretStr(secrets.token_urlsafe(48))
        return self

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"

    @property
    def site_verification_required(self) -> bool:
        if self.require_site_verification is None:
            return self.is_production
        return self.require_site_verification

    @property
    def secure_cookies(self) -> bool:
        return self.is_production if self.cookie_secure is None else self.cookie_secure

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.api_cors_origins.split(",") if origin.strip()]

    @property
    def trusted_origins(self) -> set[str]:
        """Origins allowed to make state-changing, cookie-authenticated requests."""
        origins = {origin.rstrip("/") for origin in self.cors_origins}
        origins.add(self.public_app_url.rstrip("/"))
        return origins

    @property
    def redis_needed(self) -> bool:
        return self.redis_required or self.queue_backend == "redis"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
