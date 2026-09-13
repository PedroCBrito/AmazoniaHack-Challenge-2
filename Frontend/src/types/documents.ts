import type { DocumentType, ExtractionResult } from "./extraction";

export interface DocumentSummary {
  id: number;
  image_basename: string;
  created_at: string;
  ocr_model: string;
  status: "extracted" | "ocr_only";
  document_type: DocumentType | null;
  number: string | null;
  municipality: string | null;
}

export interface DocumentList {
  items: DocumentSummary[];
  total: number;
  limit: number;
  offset: number;
}

export interface DocumentDetail extends DocumentSummary {
  extraction: ExtractionResult | null;
  ocr: {
    content: string;
    model_version: string;
    duration_ms: number;
    warnings: string[];
    regions: {
      id: string;
      text: string | null;
      page: number;
      kind: string | null;
      bounding_box: number[] | null;
    }[];
  };
}
