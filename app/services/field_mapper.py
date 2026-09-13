import json
from typing import Protocol

import httpx
from pydantic import ValidationError

from app.schemas.extraction import (
    ExtractionResult,
    FieldStatus,
)
from app.schemas.ocr import OCRResult
from app.core.errors import ApplicationError
from app.services.field_candidates import CandidateCatalog, build_candidate_catalog
from app.services.mapping_result import build_empty_result, build_mapping_result
from app.services.mapping_selection import (
    MappingSelection,
    constrained_selection_schema,
    iter_candidate_ids,
)


SYSTEM_PROMPT = """Map OCR evidence to the requested environmental-document fields.
Return null or [] whenever the evidence is absent or unclear. Never invent, complete,
correct, or combine text. Select only candidate_id values from the supplied catalog.
document_type and party roles are the only normalized values. Numbers, identifiers,
dates, coordinates, names, and prose are copied by the server from selected candidates.
Each referenced document is separate. Put form-specific labelled values in fields."""


class FieldMapper(Protocol):
    async def map(self, ocr: OCRResult) -> ExtractionResult: ...


class LlamaCppFieldMapper:
    """Select OCR-backed field candidates through llama.cpp structured output."""

    def __init__(
        self,
        http_client: httpx.AsyncClient,
        model_name: str,
        max_output_tokens: int = 4096,
    ) -> None:
        self._http_client = http_client
        self._model_name = model_name
        self._max_output_tokens = max_output_tokens

    async def map(self, ocr: OCRResult) -> ExtractionResult:
        catalog = build_candidate_catalog(ocr)
        if not catalog.items:
            return build_empty_result(
                ocr,
                self._model_name,
                "ocr_text_empty",
                "OCR returned no usable text candidates.",
            )
        payload = _request_payload(catalog, self._model_name, self._max_output_tokens)
        response = await self._request_completion(payload)
        selection, usage = _parse_completion(response)
        _validate_candidate_ids(selection, catalog)
        try:
            return build_mapping_result(
                selection, catalog, ocr, self._model_name, usage
            )
        except (ValidationError, ValueError) as exc:
            raise _invalid_response() from exc

    async def _request_completion(self, payload: dict[str, object]) -> httpx.Response:
        try:
            response = await self._http_client.post("chat/completions", json=payload)
        except httpx.TimeoutException as exc:
            raise ApplicationError(
                504, "mapper_timeout", "The local field mapper timed out."
            ) from exc
        except httpx.RequestError as exc:
            raise ApplicationError(
                503, "mapper_unavailable", "The local field mapper is unavailable."
            ) from exc
        if response.status_code in {429, 503} or response.status_code >= 500:
            raise ApplicationError(
                503, "mapper_unavailable", "The local field mapper is unavailable."
            )
        if response.is_error:
            raise ApplicationError(
                502, "mapper_failed", "The local field mapper rejected the request."
            )
        return response


class PendingFieldMapper:
    """Safe placeholder until the compact text model integration is selected."""

    def __init__(self, model_name: str) -> None:
        self._model_name = model_name

    async def map(self, ocr: OCRResult) -> ExtractionResult:
        explanation = "The field-mapping model has not been configured yet."
        return build_empty_result(
            ocr,
            self._model_name,
            "field_mapping_not_configured",
            explanation,
            FieldStatus.NOT_PROCESSED,
        )


def _request_payload(
    catalog: CandidateCatalog, model_name: str, max_output_tokens: int
) -> dict[str, object]:
    candidates = [
        {
            "id": item.id,
            "value": item.value,
            "source": item.source_excerpt,
            "region": item.region_reference,
            "kind": item.kind,
        }
        for item in catalog.items
    ]
    return {
        "model": model_name,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps({"candidates": candidates})},
        ],
        "temperature": 0,
        "max_tokens": max_output_tokens,
        "reasoning_effort": "none",
        "chat_template_kwargs": {"enable_thinking": False},
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "environmental_document_mapping",
                "strict": True,
                "schema": constrained_selection_schema(catalog.ids),
            },
        },
    }


def _parse_completion(
    response: httpx.Response,
) -> tuple[MappingSelection, dict[str, int | float | str | None] | None]:
    try:
        body = response.json()
        content = body["choices"][0]["message"]["content"]
        if not isinstance(content, str):
            raise TypeError("Completion content must be text")
        selection = MappingSelection.model_validate_json(content)
        raw_usage = body.get("usage")
        if raw_usage is not None and not isinstance(raw_usage, dict):
            raise TypeError("Completion usage must be an object")
        usage = (
            {
                key: value
                for key, value in raw_usage.items()
                if value is None or isinstance(value, (int, float, str))
            }
            if raw_usage is not None
            else None
        )
        return selection, usage
    except (KeyError, IndexError, TypeError, ValueError, ValidationError) as exc:
        raise _invalid_response() from exc


def _validate_candidate_ids(
    selection: MappingSelection, catalog: CandidateCatalog
) -> None:
    valid_ids = set(catalog.ids)
    if any(candidate_id not in valid_ids for candidate_id in iter_candidate_ids(selection)):
        raise _invalid_response()


def _invalid_response() -> ApplicationError:
    return ApplicationError(
        502,
        "invalid_mapper_response",
        "The local field mapper returned an invalid structured response.",
    )
