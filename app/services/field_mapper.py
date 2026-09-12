from typing import Protocol

from app.schemas.extraction import (
    COMMON_FIELDS,
    Confidence,
    ExtractionMeta,
    ExtractionResult,
    ExtractionWarning,
    FieldReview,
    FieldStatus,
)
from app.schemas.ocr import OCRResult


class FieldMapper(Protocol):
    async def map(self, ocr: OCRResult) -> ExtractionResult: ...


class PendingFieldMapper:
    """Safe placeholder until the compact text model integration is selected."""

    def __init__(self, model_name: str) -> None:
        self._model_name = model_name

    async def map(self, ocr: OCRResult) -> ExtractionResult:
        explanation = "The field-mapping model has not been configured yet."
        review = {
            field: FieldReview(
                status=FieldStatus.NOT_PROCESSED,
                explanation=explanation,
            )
            for field in COMMON_FIELDS
        }
        warnings = [
            ExtractionWarning(
                code="field_mapping_not_configured",
                message=explanation,
            ),
            *(
                ExtractionWarning(code="ocr_warning", message=message)
                for message in ocr.warnings
            ),
        ]
        return ExtractionResult(
            document_type=None,
            number=None,
            series=None,
            year=None,
            issued_date=None,
            issued_time=None,
            municipality=None,
            agency=None,
            parties=None,
            property_name=None,
            car=None,
            coordinates=None,
            area_ha=None,
            legal_basis=None,
            fine_brl=None,
            references=None,
            officer_registration=None,
            signatures=None,
            confidence=Confidence.zeroed(),
            meta=ExtractionMeta(
                ocr_model=ocr.model_version,
                mapper_model=self._model_name,
                duration_ms=0,
            ),
            review=review,
            warnings=warnings,
        )
