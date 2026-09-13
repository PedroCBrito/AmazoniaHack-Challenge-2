import pytest
from pydantic import ValidationError

from app.schemas.extraction import COMMON_FIELDS, Confidence, ExtractionResult


pytestmark = pytest.mark.anyio


async def _payload():
    return {
        **{name: None for name in COMMON_FIELDS},
        "confidence": Confidence.zeroed().model_dump(),
        "meta": {"ocr_model": "test", "mapper_model": "test", "duration_ms": 0},
        "review": {name: {"status": "unknown"} for name in COMMON_FIELDS},
        "warnings": [],
    }


async def test_coordinates_are_verbatim_list_and_numbered_fields_have_confidence():
    payload = await _payload()
    coordinates = ['2°58\'36,2"S 54°12\'01,0"W', '2°58\'37,3"S 54°12\'02,0"W']
    payload["coordinates"] = coordinates
    payload["fields"] = {"01": "Município: São Félix do Xingu"}
    for name in ("coordinates", "fields"):
        payload["review"][name] = {"status": "extracted", "source_excerpt": "source"}
        payload["confidence"][name] = 0.6
    result = ExtractionResult.model_validate(payload)
    assert result.coordinates == coordinates
    assert set(result.confidence.model_dump()) == set(COMMON_FIELDS)
    assert "_review" in result.model_dump(by_alias=True)
    assert ExtractionResult.model_validate_json(result.model_dump_json(by_alias=True)) == result
    payload["coordinates"] = coordinates[0]
    with pytest.raises(ValidationError):
        ExtractionResult.model_validate(payload)


@pytest.mark.parametrize("change", ["null_confidence", "extracted_null", "no_evidence", "missing_review", "extra_review"])
async def test_incoherent_review_is_rejected(change):
    payload = await _payload()
    if change == "null_confidence":
        payload["confidence"]["number"] = 0.8
    elif change == "extracted_null":
        payload["review"]["number"]["status"] = "extracted"
    elif change == "no_evidence":
        payload["number"] = "00831"
        payload["review"]["number"]["status"] = "extracted"
    elif change == "missing_review":
        del payload["review"]["number"]
    else:
        payload["review"]["invented"] = {"status": "unknown"}
    with pytest.raises(ValidationError):
        ExtractionResult.model_validate(payload)
