import json

import httpx
import pytest

from app.core.errors import ApplicationError
from app.schemas.ocr import OCRRegion, OCRResult
from app.services.field_mapper import LlamaCppFieldMapper


pytestmark = pytest.mark.anyio


def _ocr(*lines: str) -> OCRResult:
    return OCRResult(
        content="\n".join(lines),
        regions=[
            OCRRegion(id=f"r{index}", text=line)
            for index, line in enumerate(lines, start=1)
        ],
        model_version="test-ocr",
        duration_ms=5,
    )


def _blank_selection() -> dict[str, object]:
    return {
        "document_type": None,
        "number": None,
        "series": None,
        "year": None,
        "issued_date": None,
        "issued_time": None,
        "municipality": None,
        "agency": None,
        "parties": [],
        "property_name": None,
        "car": None,
        "coordinates": [],
        "area_ha": None,
        "legal_basis": [],
        "fine_brl": None,
        "references": [],
        "officer_registration": None,
        "signatures": None,
        "fields": [],
    }


def _completion(selection: dict[str, object]) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "choices": [{"message": {"content": json.dumps(selection)}}],
            "usage": {
                "prompt_tokens": 40,
                "completion_tokens": 12,
                "prompt_tokens_details": {"cached_tokens": 3},
            },
        },
    )


async def test_mapper_can_only_copy_model_selected_candidates() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert request.url.path == "/v1/chat/completions"
        assert payload["reasoning_effort"] == "none"
        assert payload["chat_template_kwargs"] == {"enable_thinking": False}
        schema = payload["response_format"]["json_schema"]
        assert schema["strict"] is True
        candidates = json.loads(payload["messages"][1]["content"])["candidates"]
        by_value = {item["value"]: item["id"] for item in candidates}
        selection = _blank_selection()
        selection.update(
            document_type={
                "value": "infraction_notice",
                "evidence": {"candidate_id": by_value["AUTO DE INFRAÇÃO"]},
            },
            number={"candidate_id": by_value["000123"]},
            year={"candidate_id": by_value["2026"]},
            fine_brl={"candidate_id": by_value["R$ 1.234,56"]},
        )
        return _completion(selection)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://mapper.test/v1"
    ) as client:
        result = await LlamaCppFieldMapper(client, "test-model").map(
            _ocr(
                "AUTO DE INFRAÇÃO",
                "Número: 000123",
                "Ano: 2026",
                "Multa: R$ 1.234,56",
            )
        )

    assert result.document_type == "infraction_notice"
    assert result.number == "000123"
    assert result.year == "2026"
    assert result.fine_brl == 1234.56
    assert result.review["number"].evidence[0].region_reference == "r2"
    assert result.confidence.number < 0.8
    assert result.meta.usage == {"prompt_tokens": 40, "completion_tokens": 12}


async def test_mapper_rejects_unknown_candidate_ids() -> None:
    selection = _blank_selection()
    selection["number"] = {"candidate_id": "invented"}
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: _completion(selection)),
        base_url="http://mapper.test/v1",
    ) as client:
        with pytest.raises(ApplicationError) as caught:
            await LlamaCppFieldMapper(client, "test-model").map(_ocr("Número: 1"))

    assert caught.value.status_code == 502
    assert caught.value.code == "invalid_mapper_response"


async def test_mapper_reports_unavailable_local_model() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("private failure", request=request)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://mapper.test/v1"
    ) as client:
        with pytest.raises(ApplicationError) as caught:
            await LlamaCppFieldMapper(client, "test-model").map(_ocr("Número: 1"))

    assert caught.value.status_code == 503
    assert caught.value.code == "mapper_unavailable"
    assert "private failure" not in caught.value.message


async def test_empty_ocr_does_not_call_model_or_invent_values() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        raise AssertionError("empty OCR must not call the mapper")

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://mapper.test/v1"
    ) as client:
        result = await LlamaCppFieldMapper(client, "test-model").map(_ocr(""))

    assert result.number is None
    assert result.review["number"].status == "not_present"
    assert result.warnings[0].code == "ocr_text_empty"
