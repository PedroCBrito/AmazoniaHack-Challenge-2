import pytest
from pydantic import ValidationError

from app.schemas.extraction import (
    COMMON_FIELDS,
    Confidence,
    DocumentReference,
    Evidence,
    ExtractionMeta,
    ExtractionResult,
    FieldReview,
    FieldStatus,
)


def _result(**changes: object) -> ExtractionResult:
    values: dict[str, object] = {field: None for field in COMMON_FIELDS}
    values.update(
        confidence=Confidence.zeroed(),
        meta=ExtractionMeta(
            ocr_model="test-ocr",
            mapper_model="test-mapper",
            duration_ms=0,
        ),
        review={
            field: FieldReview(status=FieldStatus.NOT_PRESENT)
            for field in COMMON_FIELDS
        },
        warnings=[],
    )
    values.update(changes)
    return ExtractionResult.model_validate(values)


def test_contract_preserves_coordinates_fields_and_reference_series() -> None:
    result = _result(
        coordinates=['2°58\'36,2"S', '47°21\'18,0"W'],
        fields={"7. Observações": "Texto manuscrito"},
        references=[
            DocumentReference(
                document_type="finding_notice",
                number="00318",
                series="E22",
                year="2026",
            )
        ],
        review={
            **{
                field: FieldReview(status=FieldStatus.NOT_PRESENT)
                for field in COMMON_FIELDS
            },
            "coordinates": FieldReview(
                status=FieldStatus.EXTRACTED,
                evidence=[Evidence(source_excerpt='2°58\'36,2"S')],
            ),
            "fields": FieldReview(
                status=FieldStatus.EXTRACTED,
                evidence=[Evidence(source_excerpt="7. Observações: Texto manuscrito")],
            ),
            "references": FieldReview(
                status=FieldStatus.EXTRACTED,
                evidence=[Evidence(source_excerpt="Auto 00318 E22/2026")],
            ),
        },
    )

    assert result.coordinates == ['2°58\'36,2"S', '47°21\'18,0"W']
    assert result.fields == {"7. Observações": "Texto manuscrito"}
    assert result.references[0].series == "E22"
    assert "fields" in type(result.confidence).model_fields


def test_non_null_value_requires_source_evidence() -> None:
    with pytest.raises(ValidationError, match="number requires source evidence"):
        _result(
            number="00831",
            review={
                field: FieldReview(
                    status=(
                        FieldStatus.EXTRACTED
                        if field == "number"
                        else FieldStatus.NOT_PRESENT
                    )
                )
                for field in COMMON_FIELDS
            },
        )


def test_evidence_requires_non_empty_source_text() -> None:
    with pytest.raises(ValidationError):
        Evidence(source_excerpt="")


def test_null_value_cannot_be_marked_extracted() -> None:
    with pytest.raises(ValidationError, match="number is null"):
        _result(
            review={
                field: FieldReview(
                    status=(
                        FieldStatus.EXTRACTED
                        if field == "number"
                        else FieldStatus.NOT_PRESENT
                    ),
                    evidence=(
                        [Evidence(source_excerpt="Nº ilegível")]
                        if field == "number"
                        else []
                    ),
                )
                for field in COMMON_FIELDS
            }
        )


def test_api_aliases_are_accepted_and_serialized() -> None:
    result = _result()
    payload = result.model_dump(by_alias=True)

    assert "_meta" in payload and "meta" not in payload
    assert ExtractionResult.model_validate(payload).meta.ocr_model == "test-ocr"


def test_reference_document_type_rejects_unknown_values() -> None:
    with pytest.raises(ValidationError):
        DocumentReference(
            document_type="invented_notice",
            number="1",
            series=None,
            year="2026",
        )
