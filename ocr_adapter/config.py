from functools import lru_cache

from typing import Literal

from pydantic import AliasChoices, Field, HttpUrl, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class OCRSettings(BaseSettings):
    """OCR adapter settings loaded from OCR_* environment variables."""

    model_config = SettingsConfigDict(env_prefix="OCR_", extra="ignore")

    provider: Literal["chandra", "textract"] = "chandra"

    backend_base_url: HttpUrl = HttpUrl("http://127.0.0.1:9099/v1")
    backend_model: str = Field(default="chandra-ocr", min_length=1)
    backend_api_key: SecretStr | None = None
    backend_timeout_seconds: float = Field(default=90, gt=0)
    model_version: str = Field(
        default="chandra-ocr-2.Q8_0+mmproj-f16", min_length=1
    )
    max_output_tokens: int = Field(default=12_384, ge=1)
    max_concurrent_requests: int = Field(default=1, ge=1)
    max_file_size_bytes: int = Field(default=15 * 1024 * 1024, ge=1)
    max_image_pixels: int = Field(default=40_000_000, ge=1)
    aws_region: str = Field(
        default="eu-central-1",
        validation_alias=AliasChoices("AWS_REGION", "AWS_DEFAULT_REGION", "OCR_AWS_REGION"),
    )
    aws_profile: str | None = Field(
        default=None, validation_alias=AliasChoices("AWS_PROFILE", "OCR_AWS_PROFILE")
    )

    @property
    def normalized_backend_url(self) -> str:
        """Return a base URL that preserves its API path during relative requests."""
        return f"{str(self.backend_base_url).rstrip('/')}/"

    @property
    def backend_headers(self) -> dict[str, str]:
        """Return an authorization header only when a key is configured."""
        if self.backend_api_key is None:
            return {}
        value = self.backend_api_key.get_secret_value()
        return {"Authorization": f"Bearer {value}"} if value else {}


@lru_cache
def get_settings() -> OCRSettings:
    """Load and cache validated adapter settings."""
    return OCRSettings()
