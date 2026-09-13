import re
from datetime import datetime
from enum import StrEnum
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class DocumentType(StrEnum):
    FINDING_NOTICE = "finding_notice"
    INFRACTION_NOTICE = "infraction_notice"
    EMBARGO_NOTICE = "embargo_notice"
    SEIZURE_NOTICE = "seizure_notice"
    NOTIFICATION = "notification"
    INSPECTION_ORDER = "inspection_order"
    COMPLAINT_RECORD = "complaint_record"
    INSPECTION_REPORT = "inspection_report"
    CASE_FILE_COVER = "case_file_cover"
    DEFORESTATION_VALIDATION = "deforestation_validation"


class PartyRole(StrEnum):
    CITED_PARTY = "cited_party"
    ISSUER = "issuer"
    WITNESS = "witness"
    FOUND_ON_SITE = "found_on_site"
    REPRESENTATIVE = "representative"


class FieldStatus(StrEnum):
    EXTRACTED = "extracted"
    NOT_PRESENT = "not_present"
    EXPLICITLY_ABSENT = "explicitly_absent"
    UNREADABLE = "unreadable"
    AMBIGUOUS = "ambiguous"
    NOT_PROCESSED = "not_processed"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class Party(StrictModel):
    role: PartyRole
    name: str | None
    document_id: str | None
    address: str | None


class DocumentReference(StrictModel):
    document_type: DocumentType | None
    number: str | None
    series: str | None
    year: str | None


class SignatureDescriptions(StrictModel):
    issuer: str | None
    cited_party: str | None


class Confidence(StrictModel):
    document_type: float = Field(ge=0, le=1)
    number: float = Field(ge=0, le=1)
    series: float = Field(ge=0, le=1)
    year: float = Field(ge=0, le=1)
    issued_date: float = Field(ge=0, le=1)
    issued_time: float = Field(ge=0, le=1)
    municipality: float = Field(ge=0, le=1)
    agency: float = Field(ge=0, le=1)
    parties: float = Field(ge=0, le=1)
    property_name: float = Field(ge=0, le=1)
    car: float = Field(ge=0, le=1)
    coordinates: float = Field(ge=0, le=1)
    area_ha: float = Field(ge=0, le=1)
    legal_basis: float = Field(ge=0, le=1)
    fine_brl: float = Field(ge=0, le=1)
    references: float = Field(ge=0, le=1)
    officer_registration: float = Field(ge=0, le=1)
    signatures: float = Field(ge=0, le=1)
    fields: float = Field(ge=0, le=1)

    @classmethod
    def zeroed(cls) -> "Confidence":
        return cls(**{name: 0.0 for name in cls.model_fields})


class Evidence(StrictModel):
    source_excerpt: str = Field(min_length=1)
    region_reference: str | None = None
    bounding_box: list[int] | None = Field(default=None, min_length=4, max_length=4)


class FieldReview(StrictModel):
    status: FieldStatus
    evidence: list[Evidence] = Field(default_factory=list)
    explanation: str | None = None


class ExtractionWarning(StrictModel):
    code: str
    message: str
    field: str | None = None


class ExtractionMeta(StrictModel):
    document_id: int | None = Field(default=None, ge=1)
    ocr_model: str
    mapper_model: str
    duration_ms: int = Field(ge=0)
    usage: dict[str, int | float | str | None] | None = None
    review_required: Literal[True] = True
    confidence_kind: Literal["heuristic"] = "heuristic"


class ExtractionResult(StrictModel):
    document_type: DocumentType | None
    number: str | None
    series: str | None
    year: str | None
    issued_date: str | None
    issued_time: str | None
    municipality: str | None
    agency: str | None
    parties: list[Party] | None
    property_name: str | None
    car: str | None
    coordinates: list[str] | None
    area_ha: float | None = Field(ge=0, allow_inf_nan=False)
    legal_basis: list[str] | None
    fine_brl: float | None = Field(ge=0, allow_inf_nan=False)
    references: list[DocumentReference] | None
    officer_registration: str | None
    signatures: SignatureDescriptions | None
    fields: dict[str, str | None] | None
    confidence: Confidence
    meta: ExtractionMeta = Field(alias="_meta")
    review: dict[str, FieldReview] = Field(alias="_review")
    warnings: list[ExtractionWarning] = Field(alias="_warnings")

    @field_validator("issued_date")
    @classmethod
    def validate_issued_date(cls, value: str | None) -> str | None:
        if value is None:
            return value
        if not re.fullmatch(r"\d{2}/\d{2}/\d{4}", value):
            raise ValueError("issued_date must use DD/MM/YYYY")
        try:
            datetime.strptime(value, "%d/%m/%Y")
        except ValueError as exc:
            raise ValueError("issued_date must be a valid calendar date") from exc
        return value

    @field_validator("issued_time")
    @classmethod
    def validate_issued_time(cls, value: str | None) -> str | None:
        if value is None:
            return value
        if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value):
            raise ValueError("issued_time must use HH:MM")
        return value

    @model_validator(mode="after")
    def validate_review_metadata(self) -> Self:
        common_fields = set(Confidence.model_fields)
        missing = common_fields.difference(self.review)
        if missing:
            missing_names = ", ".join(sorted(missing))
            raise ValueError(f"review metadata is missing fields: {missing_names}")
        unknown = set(self.review).difference(common_fields)
        if unknown:
            unknown_names = ", ".join(sorted(unknown))
            raise ValueError(f"review metadata has unknown fields: {unknown_names}")
        for field in common_fields:
            self._validate_field_review(field, self.review[field])
        return self

    def _validate_field_review(self, field: str, review: FieldReview) -> None:
        value = getattr(self, field)
        if value is None and review.status == FieldStatus.EXTRACTED:
            raise ValueError(f"{field} is null but marked extracted")
        if value is not None and not review.evidence:
            raise ValueError(f"{field} requires source evidence")
        allowed = {FieldStatus.EXTRACTED, FieldStatus.AMBIGUOUS}
        if value is not None and review.status not in allowed:
            raise ValueError(f"{field} has a value but status is {review.status}")


COMMON_FIELDS = tuple(Confidence.model_fields)
