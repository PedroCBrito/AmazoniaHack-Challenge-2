import { api } from "./client";
import type { ExtractionResult } from "../types/extraction";
import type { DocumentDetail, DocumentList } from "../types/documents";

export async function extractDocument(file: File): Promise<ExtractionResult> {
  return api.postFile<ExtractionResult>("/extract", file, "image");
}

export function listDocuments(offset = 0, signal?: AbortSignal): Promise<DocumentList> {
  return api.get(`/documents?limit=20&offset=${offset}`, signal);
}

export function getDocument(id: string, signal?: AbortSignal): Promise<DocumentDetail> {
  return api.get(`/documents/${encodeURIComponent(id)}`, signal);
}
