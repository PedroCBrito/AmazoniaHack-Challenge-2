from typing import Literal

from pydantic import BaseModel

from app.schemas.extraction import ExtractionResult
from app.schemas.ocr import OCRResult


class DocumentSummary(BaseModel):
    id: int
    image_basename: str
    created_at: str
    ocr_model: str
    status: Literal["extracted", "ocr_only"]
    document_type: str | None = None
    number: str | None = None
    municipality: str | None = None


class DocumentList(BaseModel):
    items: list[DocumentSummary]
    total: int
    limit: int
    offset: int


class DocumentDetail(DocumentSummary):
    ocr: OCRResult
    extraction: ExtractionResult | None
