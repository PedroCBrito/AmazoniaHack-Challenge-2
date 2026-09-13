from dataclasses import dataclass, field

from app.schemas.extraction import (
    COMMON_FIELDS,
    Confidence,
    DocumentReference,
    Evidence,
    ExtractionMeta,
    ExtractionResult,
    ExtractionWarning,
    FieldReview,
    FieldStatus,
    Party,
    SignatureDescriptions,
)
from app.schemas.ocr import OCRResult
from app.services.field_candidates import CandidateCatalog, FieldCandidate
from app.services.field_validation import is_valid_date, is_valid_time, parse_decimal
from app.services.mapping_selection import (
    CandidateSelection,
    MappingSelection,
    PartySelection,
    ReferenceSelection,
)


SCALAR_FIELDS = (
    "number",
    "series",
    "year",
    "municipality",
    "agency",
    "property_name",
    "car",
    "officer_registration",
)


@dataclass(slots=True)
class _Resolved:
    values: dict[str, object] = field(default_factory=dict)
    invalid: dict[str, str] = field(default_factory=dict)
    warnings: list[ExtractionWarning] = field(default_factory=list)


def build_mapping_result(
    selection: MappingSelection,
    catalog: CandidateCatalog,
    ocr: OCRResult,
    mapper_model: str,
    usage: dict[str, int | float | str | None] | None,
) -> ExtractionResult:
    resolved = _resolve_values(selection, catalog)
    reviews = _build_reviews(selection, catalog, resolved)
    confidence = _build_confidence(reviews, bool(ocr.warnings))
    warnings = [
        *(ExtractionWarning(code="ocr_warning", message=item) for item in ocr.warnings),
        *resolved.warnings,
    ]
    if catalog.truncated:
        warnings.append(ExtractionWarning(
            code="candidate_limit_reached",
            message="Only the first 200 OCR candidates were mapped.",
        ))
    return ExtractionResult(
        **resolved.values,
        confidence=confidence,
        meta=ExtractionMeta(
            ocr_model=ocr.model_version,
            mapper_model=mapper_model,
            duration_ms=0,
            usage=usage,
        ),
        review=reviews,
        warnings=warnings,
    )


def build_empty_result(
    ocr: OCRResult,
    mapper_model: str,
    warning_code: str,
    message: str,
    status: FieldStatus = FieldStatus.NOT_PRESENT,
) -> ExtractionResult:
    review = {
        name: FieldReview(status=status, explanation=message)
        for name in COMMON_FIELDS
    }
    return ExtractionResult(
        **{name: None for name in COMMON_FIELDS},
        confidence=Confidence.zeroed(),
        meta=ExtractionMeta(
            ocr_model=ocr.model_version,
            mapper_model=mapper_model,
            duration_ms=0,
        ),
        review=review,
        warnings=[
            ExtractionWarning(code=warning_code, message=message),
            *(ExtractionWarning(code="ocr_warning", message=item) for item in ocr.warnings),
        ],
    )


def _resolve_values(selection: MappingSelection, catalog: CandidateCatalog) -> _Resolved:
    resolved = _Resolved()
    for name in SCALAR_FIELDS:
        resolved.values[name] = _value(getattr(selection, name), catalog)
    resolved.values["document_type"] = (
        selection.document_type.value if selection.document_type else None
    )
    _resolve_formatted_values(selection, catalog, resolved)
    resolved.values["parties"] = _resolve_parties(selection.parties, catalog)
    resolved.values["coordinates"] = _resolve_list(selection.coordinates, catalog)
    resolved.values["legal_basis"] = _resolve_list(selection.legal_basis, catalog)
    resolved.values["references"] = _resolve_references(selection.references, catalog)
    resolved.values["signatures"] = _resolve_signatures(selection, catalog)
    resolved.values["fields"] = _resolve_fields(selection, catalog)
    return resolved


def _resolve_formatted_values(
    selection: MappingSelection,
    catalog: CandidateCatalog,
    resolved: _Resolved,
) -> None:
    checks = {
        "issued_date": is_valid_date,
        "issued_time": is_valid_time,
    }
    for name, check in checks.items():
        raw = _value(getattr(selection, name), catalog)
        resolved.values[name] = raw if raw is None or check(raw) else None
        if raw is not None and resolved.values[name] is None:
            _mark_invalid(resolved, name, f"Invalid {name} format in OCR candidate.")
    for name in ("area_ha", "fine_brl"):
        raw = _value(getattr(selection, name), catalog)
        parsed = parse_decimal(raw) if raw is not None else None
        resolved.values[name] = parsed
        if raw is not None and parsed is None:
            _mark_invalid(resolved, name, f"Invalid {name} number in OCR candidate.")


def _mark_invalid(resolved: _Resolved, name: str, message: str) -> None:
    resolved.invalid[name] = message
    resolved.warnings.append(ExtractionWarning(
        code="field_format_invalid",
        field=name,
        message=message,
    ))


def _resolve_parties(
    selected: list[PartySelection], catalog: CandidateCatalog
) -> list[Party] | None:
    parties = [
        Party(
            role=item.role,
            name=_value(item.name, catalog),
            document_id=_value(item.document_id, catalog),
            address=_value(item.address, catalog),
        )
        for item in selected
    ]
    return parties or None


def _resolve_references(
    selected: list[ReferenceSelection], catalog: CandidateCatalog
) -> list[DocumentReference] | None:
    references = [
        DocumentReference(
            document_type=(item.document_type.value if item.document_type else None),
            number=_value(item.number, catalog),
            series=_value(item.series, catalog),
            year=_value(item.year, catalog),
        )
        for item in selected
    ]
    return references or None


def _resolve_signatures(
    selection: MappingSelection, catalog: CandidateCatalog
) -> SignatureDescriptions | None:
    if selection.signatures is None:
        return None
    signatures = SignatureDescriptions(
        issuer=_value(selection.signatures.issuer, catalog),
        cited_party=_value(selection.signatures.cited_party, catalog),
    )
    return signatures if signatures.issuer or signatures.cited_party else None


def _resolve_fields(
    selection: MappingSelection, catalog: CandidateCatalog
) -> dict[str, str | None] | None:
    values = {
        _required_value(item.label, catalog): _required_value(item.value, catalog)
        for item in selection.fields
    }
    return values or None


def _resolve_list(
    selected: list[CandidateSelection], catalog: CandidateCatalog
) -> list[str] | None:
    values = [_required_value(item, catalog) for item in selected]
    return values or None


def _build_reviews(
    selection: MappingSelection,
    catalog: CandidateCatalog,
    resolved: _Resolved,
) -> dict[str, FieldReview]:
    reviews: dict[str, FieldReview] = {}
    for name in COMMON_FIELDS:
        candidates = _field_candidates(name, selection, catalog)
        evidence = [_evidence(item) for item in _unique_candidates(candidates)]
        value = resolved.values[name]
        status = FieldStatus.EXTRACTED if value is not None else FieldStatus.NOT_PRESENT
        explanation = None
        if name in resolved.invalid:
            status = FieldStatus.UNREADABLE
            explanation = resolved.invalid[name]
        reviews[name] = FieldReview(
            status=status,
            evidence=evidence,
            explanation=explanation,
        )
    return reviews


def _field_candidates(
    name: str, selection: MappingSelection, catalog: CandidateCatalog
) -> list[FieldCandidate]:
    selected = getattr(selection, name)
    ids = _candidate_ids(selected)
    return [_required_candidate(candidate_id, catalog) for candidate_id in ids]


def _candidate_ids(value: object) -> list[str]:
    if isinstance(value, CandidateSelection):
        return [value.candidate_id]
    if hasattr(value, "__class__") and hasattr(value.__class__, "model_fields"):
        ids: list[str] = []
        for name in value.__class__.model_fields:
            ids.extend(_candidate_ids(getattr(value, name)))
        return ids
    if isinstance(value, list):
        return [candidate_id for item in value for candidate_id in _candidate_ids(item)]
    return []


def _unique_candidates(candidates: list[FieldCandidate]) -> list[FieldCandidate]:
    return list({item.id: item for item in candidates}.values())


def _evidence(candidate: FieldCandidate) -> Evidence:
    return Evidence(
        source_excerpt=candidate.source_excerpt,
        region_reference=candidate.region_reference,
        bounding_box=(list(candidate.bounding_box) if candidate.bounding_box else None),
    )


def _build_confidence(
    reviews: dict[str, FieldReview], has_ocr_warnings: bool
) -> Confidence:
    extracted_score = 0.55 if has_ocr_warnings else 0.65
    scores = {
        name: (
            extracted_score
            if review.status == FieldStatus.EXTRACTED
            else 0.20 if review.status == FieldStatus.UNREADABLE else 0.0
        )
        for name, review in reviews.items()
    }
    return Confidence(**scores)


def _value(
    selected: CandidateSelection | None, catalog: CandidateCatalog
) -> str | None:
    return _required_value(selected, catalog) if selected else None


def _required_value(selected: CandidateSelection, catalog: CandidateCatalog) -> str:
    return _required_candidate(selected.candidate_id, catalog).value


def _required_candidate(candidate_id: str, catalog: CandidateCatalog) -> FieldCandidate:
    candidate = catalog.get(candidate_id)
    if candidate is None:
        raise ValueError(f"Unknown OCR candidate: {candidate_id}")
    return candidate

