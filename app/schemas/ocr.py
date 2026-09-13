from pydantic import BaseModel, ConfigDict, Field


class OCRRegion(BaseModel):
    """A source region exposed by the project's Chandra wrapper."""

    model_config = ConfigDict(extra="allow")

    id: str
    text: str | None = None
    page: int = Field(default=1, ge=1)
    kind: str | None = None
    bounding_box: list[int] | None = Field(default=None, min_length=4, max_length=4)


class OCRResult(BaseModel):
    """Expected response from POST /ocr on the internal OCR service."""

    model_config = ConfigDict(extra="forbid")

    content: str
    regions: list[OCRRegion] = Field(default_factory=list)
    model_version: str
    duration_ms: int = Field(ge=0)
    warnings: list[str] = Field(default_factory=list)
