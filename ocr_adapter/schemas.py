from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    """Base model that rejects undocumented fields."""

    model_config = ConfigDict(extra="forbid")


class LivenessResponse(StrictModel):
    """Process liveness response."""

    status: Literal["alive"] = "alive"
    service: Literal["ocr-adapter"] = "ocr-adapter"


class HealthResponse(StrictModel):
    """Inference readiness response."""

    status: Literal["ready"] = "ready"
    model_version: str
    device: str | None = None


class OCRRegion(StrictModel):
    """One Chandra layout block in received-image pixel coordinates."""

    id: str
    text: str | None = None
    page: int = Field(default=1, ge=1)
    kind: str | None = None
    bounding_box: list[int] | None = Field(default=None, min_length=4, max_length=4)


class OCRResult(StrictModel):
    """Stable response returned to the application API."""

    content: str
    regions: list[OCRRegion] = Field(default_factory=list)
    model_version: str
    duration_ms: int = Field(ge=0)
    warnings: list[str] = Field(default_factory=list)


class ErrorDetail(StrictModel):
    """Machine-readable adapter error."""

    code: str
    message: str


class ErrorResponse(StrictModel):
    """Adapter error envelope."""

    error: ErrorDetail
