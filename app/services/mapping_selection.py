from collections.abc import Iterator
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.schemas.extraction import DocumentType, PartyRole


class StrictSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CandidateSelection(StrictSelection):
    candidate_id: str


class DocumentTypeSelection(StrictSelection):
    value: DocumentType
    evidence: CandidateSelection


class PartySelection(StrictSelection):
    role: PartyRole
    name: CandidateSelection | None
    document_id: CandidateSelection | None
    address: CandidateSelection | None


class ReferenceSelection(StrictSelection):
    document_type: DocumentTypeSelection | None
    number: CandidateSelection | None
    series: CandidateSelection | None
    year: CandidateSelection | None


class SignatureSelection(StrictSelection):
    issuer: CandidateSelection | None
    cited_party: CandidateSelection | None


class FormFieldSelection(StrictSelection):
    label: CandidateSelection
    value: CandidateSelection


class MappingSelection(StrictSelection):
    document_type: DocumentTypeSelection | None
    number: CandidateSelection | None
    series: CandidateSelection | None
    year: CandidateSelection | None
    issued_date: CandidateSelection | None
    issued_time: CandidateSelection | None
    municipality: CandidateSelection | None
    agency: CandidateSelection | None
    parties: list[PartySelection]
    property_name: CandidateSelection | None
    car: CandidateSelection | None
    coordinates: list[CandidateSelection]
    area_ha: CandidateSelection | None
    legal_basis: list[CandidateSelection]
    fine_brl: CandidateSelection | None
    references: list[ReferenceSelection]
    officer_registration: CandidateSelection | None
    signatures: SignatureSelection | None
    fields: list[FormFieldSelection]


def constrained_selection_schema(candidate_ids: tuple[str, ...]) -> dict[str, Any]:
    schema = MappingSelection.model_json_schema()
    _constrain_candidate_ids(schema, list(candidate_ids))
    return schema


def iter_candidate_ids(value: object) -> Iterator[str]:
    if isinstance(value, CandidateSelection):
        yield value.candidate_id
        return
    if isinstance(value, BaseModel):
        for field in value.__class__.model_fields:
            yield from iter_candidate_ids(getattr(value, field))
        return
    if isinstance(value, list):
        for item in value:
            yield from iter_candidate_ids(item)


def _constrain_candidate_ids(value: object, candidate_ids: list[str]) -> None:
    if isinstance(value, dict):
        properties = value.get("properties")
        if isinstance(properties, dict) and "candidate_id" in properties:
            properties["candidate_id"] = {
                "type": "string",
                "enum": candidate_ids,
            }
        for child in value.values():
            _constrain_candidate_ids(child, candidate_ids)
    elif isinstance(value, list):
        for child in value:
            _constrain_candidate_ids(child, candidate_ids)
