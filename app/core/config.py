from functools import lru_cache
from typing import Literal

from pydantic import Field, HttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from APP_* environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="APP_",
        extra="ignore",
    )

    name: str = "Environmental Document Extraction API"
    environment: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"

    chandra_base_url: HttpUrl = HttpUrl("http://127.0.0.1:9000")
    chandra_timeout_seconds: float = Field(default=90, gt=0)
    processing_deadline_seconds: float = Field(default=120, gt=0)

    max_concurrent_requests: int = Field(default=1, ge=1)
    max_file_size_bytes: int = Field(default=15 * 1024 * 1024, ge=1)
    max_image_pixels: int = Field(default=40_000_000, ge=1)

    mapper_model: str = "pending"


@lru_cache
def get_settings() -> Settings:
    return Settings()

