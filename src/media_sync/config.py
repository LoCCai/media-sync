"""Application configuration with safe local defaults."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings loaded from ``MEDIA_SYNC_*`` environment variables."""

    model_config = SettingsConfigDict(
        env_prefix="MEDIA_SYNC_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )

    state_dir: Path = Path(".media-sync")
    archive_dir: Path = Path("archive")
    export_dir: Path = Path("exports")
    job_dir: Path = Path("jobs")
    database_url: str | None = None
    api_host: str = "127.0.0.1"
    api_port: int = Field(default=8632, ge=1, le=65535)
    log_level: str = "INFO"
    default_sync_interval_seconds: int = Field(default=21_600, ge=60)
    default_max_items: int = Field(default=30, ge=1, le=1_000)
    max_crawl_seconds: int = Field(default=1_800, ge=30, le=86_400)

    @field_validator("log_level")
    @classmethod
    def normalize_log_level(cls, value: str) -> str:
        normalized = value.upper().strip()
        allowed = {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"}
        if normalized not in allowed:
            raise ValueError(f"log_level must be one of {sorted(allowed)}")
        return normalized

    @property
    def resolved_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        database_path = (self.state_dir / "media-sync.sqlite3").resolve()
        return f"sqlite+pysqlite:///{database_path.as_posix()}"

    def ensure_directories(self) -> None:
        """Create runtime roots without creating or exposing credential files."""

        for path in (self.state_dir, self.archive_dir, self.export_dir, self.job_dir):
            path.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide immutable settings snapshot."""

    return Settings()
