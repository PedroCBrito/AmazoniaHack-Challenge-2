export type DocumentType =
  | "finding_notice"
  | "infraction_notice"
  | "embargo_notice"
  | "seizure_notice"
  | "notification"
  | "inspection_order"
  | "complaint_record"
  | "inspection_report"
  | "case_file_cover"
  | "deforestation_validation";

export type PartyRole =
  | "cited_party"
  | "issuer"
  | "witness"
  | "found_on_site"
  | "representative";

export type FieldStatus =
  | "extracted"
  | "not_present"
  | "explicitly_absent"
  | "unreadable"
  | "ambiguous"
  | "not_processed";

export interface Party {
  role: PartyRole;
  name: string | null;
  document_id: string | null;
  address: string | null;
}

export interface DocumentReference {
  document_type: DocumentType | string | null;
  number: string | null;
  series: string | null;
  year: string | null;
}

export interface SignatureDescriptions {
  issuer: string | null;
  cited_party: string | null;
}

export const COMMON_FIELDS = [
  "document_type",
  "number",
  "series",
  "year",
  "issued_date",
  "issued_time",
  "municipality",
  "agency",
  "parties",
  "property_name",
  "car",
  "coordinates",
  "area_ha",
  "legal_basis",
  "fine_brl",
  "references",
  "officer_registration",
  "signatures",
  "fields",
] as const;

export type CommonField = (typeof COMMON_FIELDS)[number];

export type Confidence = Record<CommonField, number>;

export interface FieldReview {
  status: FieldStatus;
  evidence: {
    source_excerpt: string;
    region_reference: string | null;
    bounding_box: number[] | null;
  }[];
  explanation: string | null;
}

export interface ExtractionWarning {
  code: string;
  message: string;
  field: string | null;
}

export interface ExtractionMeta {
  document_id: number | null;
  ocr_model: string;
  mapper_model: string;
  duration_ms: number;
  usage: Record<string, number | string | null> | null;
  review_required: true;
  confidence_kind: "heuristic";
}

export interface ExtractionResult {
  document_type: DocumentType | null;
  number: string | null;
  series: string | null;
  year: string | null;
  issued_date: string | null;
  issued_time: string | null;
  municipality: string | null;
  agency: string | null;
  parties: Party[] | null;
  property_name: string | null;
  car: string | null;
  coordinates: string[] | null;
  area_ha: number | null;
  legal_basis: string[] | null;
  fine_brl: number | null;
  references: DocumentReference[] | null;
  officer_registration: string | null;
  signatures: SignatureDescriptions | null;
  fields: Record<string, string | null> | null;
  confidence: Confidence;
  _meta: ExtractionMeta;
  _review: Record<CommonField, FieldReview>;
  _warnings: ExtractionWarning[];
}
