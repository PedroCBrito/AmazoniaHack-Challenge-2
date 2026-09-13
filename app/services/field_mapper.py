from typing import Protocol

from pydantic import ValidationError

from app.schemas.extraction import (
    COMMON_FIELDS,
    Confidence,
    ExtractionMeta,
    ExtractionFields,
    ExtractionResult,
    ExtractionWarning,
    FieldReview,
    FieldStatus,
)
from app.schemas.ocr import OCRResult
from app.services.mapper_rules import Candidate, RuleCollector
from app.services.ocr_text import source_lines
from app.services.form_layout import assemble_form


class FieldMapper(Protocol):
    async def map(self, ocr: OCRResult) -> ExtractionResult: ...


class RuleBasedFieldMapper:
    """Map explicit Portuguese form labels with source evidence and no inference API."""

    MODEL_VERSION = "portuguese-form-rules-v2"

    async def map(self, ocr: OCRResult) -> ExtractionResult:
        candidates = RuleCollector().read(assemble_form(source_lines(ocr)))
        values = {name: None for name in COMMON_FIELDS}
        confidence = Confidence.zeroed()
        review: dict[str, FieldReview] = {}
        warnings = [ExtractionWarning(code="ocr_warning", message=message) for message in ocr.warnings]
        warnings.append(ExtractionWarning(
            code="rule_mapper_limitations",
            message="Only supported explicit titles and labels are mapped; unknown fields require image review. Confidence is heuristic, not OCR accuracy.",
        ))
        for name in COMMON_FIELDS:
            entries = candidates.get(name, [])
            value, status = _resolve(name, entries)
            evidence = []
            for entry in entries:
                for source in entry.evidence:
                    if source not in evidence:
                        evidence.append(source)
            if value is not None:
                try:
                    checked = ExtractionFields.model_validate({**values, name: value})
                    value = getattr(checked, name)
                except ValidationError:
                    value, status = None, FieldStatus.AMBIGUOUS
                    warnings.append(ExtractionWarning(
                        code="invalid_field_value", field=name,
                        message="The recognized value does not satisfy the field format.",
                    ))
            values[name] = value
            explanation = {
                FieldStatus.EXTRACTED: "Mapped from an explicit document title or field label; confirm against the image.",
                FieldStatus.UNKNOWN: "The OCR and supported rules do not establish this field; this does not prove absence in the image.",
                FieldStatus.AMBIGUOUS: "Conflicting candidates or an invalid format prevent a reliable value.",
                FieldStatus.EXPLICITLY_ABSENT: "The source explicitly states that the value is absent or not applicable.",
                FieldStatus.UNREADABLE: "The source explicitly marks this value as unreadable.",
            }[status]
            review[name] = FieldReview(
                status=status, explanation=explanation, evidence=evidence,
                source_excerpt=evidence[0].source_excerpt if evidence else None,
                region_reference=evidence[0].region_reference if evidence else None,
            )
            if value is not None:
                score = min(entry.confidence_cap for entry in entries if entry.value is not None)
                if ocr.warnings or any(entry.status != FieldStatus.EXTRACTED for entry in entries):
                    score = min(score, 0.5)
                setattr(confidence, name, score)
            for issue in sorted({issue for entry in entries for issue in entry.issues}):
                warnings.append(ExtractionWarning(code=issue, field=name, message={
                    "layout_association": "Values were associated using form layout or adjacent lines; verify the field boundaries.",
                    "ocr_coordinate_marker": "A longitude direction was recognized as digit 0. The OCR text was preserved unchanged; verify against the image.",
                }[issue]))
            if status in {FieldStatus.AMBIGUOUS, FieldStatus.UNREADABLE}:
                warnings.append(ExtractionWarning(code=f"field_{status.value}", field=name, message=explanation))
            elif value is not None and any(entry.status != FieldStatus.EXTRACTED for entry in entries):
                warnings.append(ExtractionWarning(
                    code="partial_field", field=name,
                    message="Some labeled entries could not be mapped; review all source evidence.",
                ))
        return ExtractionResult(
            **values, confidence=confidence, review=review, warnings=warnings,
            meta=ExtractionMeta(ocr_model=ocr.model_version, mapper_model=self.MODEL_VERSION, duration_ms=0),
        )


def _resolve(name: str, entries: list[Candidate]) -> tuple[object, FieldStatus]:
    present = [entry.value for entry in entries if entry.status == FieldStatus.EXTRACTED and entry.value is not None]
    statuses = {entry.status for entry in entries}
    if FieldStatus.AMBIGUOUS in statuses:
        return None, FieldStatus.AMBIGUOUS
    if present and FieldStatus.EXPLICITLY_ABSENT in statuses:
        return None, FieldStatus.AMBIGUOUS
    if not present:
        for status in (FieldStatus.UNREADABLE, FieldStatus.EXPLICITLY_ABSENT):
            if status in statuses:
                return None, status
        return None, FieldStatus.UNKNOWN
    if name in {"coordinates", "legal_basis", "references", "parties"}:
        combined = []
        for values in present:
            for value in values:
                if name == "coordinates" or value not in combined:
                    combined.append(value)
        return combined or None, FieldStatus.EXTRACTED if combined else FieldStatus.UNKNOWN
    if name in {"signatures", "fields"}:
        combined = {"issuer": None, "cited_party": None} if name == "signatures" else {}
        for value in present:
            for key, item in value.items():
                if combined.get(key) not in (None, item):
                    return None, FieldStatus.AMBIGUOUS
                combined[key] = item
        return combined, FieldStatus.EXTRACTED
    if any(value != present[0] for value in present[1:]) or FieldStatus.UNREADABLE in statuses:
        return None, FieldStatus.AMBIGUOUS
    return present[0], FieldStatus.EXTRACTED
