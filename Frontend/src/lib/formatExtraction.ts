import type {
  ExtractionResult,
  CommonField,
  FieldStatus,
  DocumentType,
} from "../types/extraction";

const FIELD_LABELS: Record<CommonField, string> = {
  document_type: "Tipo de documento",
  number: "Número",
  series: "Série",
  year: "Ano",
  issued_date: "Data de emissão",
  issued_time: "Hora de emissão",
  municipality: "Município",
  agency: "Órgão",
  parties: "Partes envolvidas",
  property_name: "Propriedade",
  car: "CAR",
  coordinates: "Coordenadas",
  area_ha: "Área (ha)",
  legal_basis: "Base legal",
  fine_brl: "Multa (R$)",
  references: "Documentos referenciados",
  officer_registration: "Matrícula do agente",
  signatures: "Assinaturas",
  fields: "Campos adicionais",
};

const DOCUMENT_TYPES: Record<DocumentType, string> = {
  finding_notice: "Auto de constatação", infraction_notice: "Auto de infração",
  embargo_notice: "Termo de embargo", seizure_notice: "Termo de apreensão",
  notification: "Notificação", inspection_order: "Ordem de fiscalização",
  complaint_record: "Registro de denúncia", inspection_report: "Relatório de fiscalização",
  case_file_cover: "Capa de processo", deforestation_validation: "Validação de desmatamento",
};

export function documentTypeLabel(type: DocumentType | null): string {
  return type ? DOCUMENT_TYPES[type] ?? type : "Tipo não identificado";
}

function formatValue(field: CommonField, result: ExtractionResult): string {
  switch (field) {
    case "document_type":
      return result.document_type ? documentTypeLabel(result.document_type) : "";
    case "parties":
      return (result.parties ?? []).map((p) => [
        ({ cited_party: "Autuado", issuer: "Emissor", witness: "Testemunha", found_on_site: "Encontrado no local", representative: "Representante" })[p.role],
        p.name, p.document_id, p.address,
      ].filter(Boolean).join(" · ")).join("\n");
    case "references":
      return (result.references ?? [])
        .map((r) => [r.document_type ? documentTypeLabel(r.document_type as DocumentType) : null, r.number, r.series ? `Série ${r.series}` : null, r.year].filter(Boolean).join(" · "))
        .join("\n");
    case "signatures":
      return [result.signatures?.issuer ? `Emissor: ${result.signatures.issuer}` : null, result.signatures?.cited_party ? `Autuado: ${result.signatures.cited_party}` : null]
        .filter(Boolean)
        .join(" · ");
    case "legal_basis":
      return (result.legal_basis ?? []).join("; ");
    case "coordinates":
      return (result.coordinates ?? []).join("\n");
    case "fields":
      return Object.entries(result.fields ?? {}).map(([key, value]) => `${key}: ${value ?? "—"}`).join("\n");
    case "area_ha":
      return result.area_ha != null ? `${result.area_ha.toLocaleString("pt-BR")} ha` : "";
    case "fine_brl":
      return result.fine_brl != null
        ? result.fine_brl.toLocaleString("pt-BR", {
            style: "currency",
            currency: "BRL",
          })
        : "";
    default: {
      const raw = result[field];
      return typeof raw === "string" ? raw : "";
    }
  }
}

export interface DisplayField {
  field: CommonField;
  label: string;
  value: string;
  confidence: number;
  status: FieldStatus;
}

export function toDisplayFields(result: ExtractionResult): DisplayField[] {
  return (Object.keys(FIELD_LABELS) as CommonField[]).map((field) => ({
    field,
    label: FIELD_LABELS[field],
    value: formatValue(field, result),
    confidence: result.confidence[field],
    status: result._review[field].status,
  }));
}
