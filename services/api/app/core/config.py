from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Fixify API"
    app_env: str = "development"
    database_url: str = (
        "postgresql+psycopg://fixify:change-me-locally@localhost:5432/fixify"
    )
    redis_url: str = "redis://localhost:6379/0"
    redis_required: bool = True
    api_cors_origins: str = "http://localhost:3000"

    model_config = SettingsConfigDict(
        env_file=("../../.env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.api_cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
