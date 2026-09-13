import { useEffect, useRef, useState } from "react";
import { Link, useLocation, useParams } from "react-router-dom";
import { getDocument } from "../api/documents";
import FieldRow from "../components/FieldRow";
import { toDisplayFields, type DisplayField } from "../lib/formatExtraction";
import type { ExtractionResult } from "../types/extraction";
import type { DocumentDetail } from "../types/documents";

interface ReviewLocationState {
  result?: ExtractionResult;
  sourceFile?: File;
}

interface EditableField extends DisplayField {
  confirmed: boolean;
}

function ReviewPage() {
  const { documentId } = useParams();
  const location = useLocation();
  return <ReviewDocument key={documentId ?? location.key} documentId={documentId} />;
}

function ReviewDocument({ documentId }: { documentId?: string }) {
  const location = useLocation();
  const state = location.state as ReviewLocationState | null;
  const [document, setDocument] = useState<DocumentDetail | null>(null);
  const [loading, setLoading] = useState(Boolean(documentId));
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  const imageRef = useRef<HTMLImageElement>(null);

  useEffect(() => {
    if (!state?.sourceFile || !imageRef.current) return;
    const url = URL.createObjectURL(state.sourceFile);
    imageRef.current.src = url;
    return () => URL.revokeObjectURL(url);
  }, [state?.sourceFile, loading, error]);

  useEffect(() => {
    if (!documentId) return;
    const controller = new AbortController();
    getDocument(documentId, controller.signal).then((data) => {
      if (!controller.signal.aborted) setDocument(data);
    }).catch((cause: unknown) => {
      if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : "Não foi possível carregar o documento.");
    }).finally(() => {
      if (!controller.signal.aborted) setLoading(false);
    });
    return () => controller.abort();
  }, [documentId, attempt]);

  const result = documentId ? document?.extraction : state?.result;

  return (
    <div className="max-w-5xl">
      <Link to="/documentos" className="text-sm text-forest underline">Voltar aos documentos</Link>
      <h2 className="mt-3 font-serif text-2xl text-ink">Revisão do documento</h2>
      {loading && <p role="status" className="mt-6 text-sm">Carregando documento...</p>}
      {error && <div role="alert" className="mt-6 text-sm text-clay">
        <p>{error}</p>
        <button onClick={() => { setLoading(true); setError(null); setAttempt((n) => n + 1); }} className="mt-2 underline">Tentar novamente</button>
      </div>}
      {!loading && !error && (
        <>
          {document && <p className="mt-2 text-sm text-ink/70">{document.image_basename} · {new Date(document.created_at).toLocaleString("pt-BR")}</p>}
          {!document && !result && <p className="mt-6 text-sm">Nenhum documento para revisar. <Link className="text-forest underline" to="/">Enviar documento</Link></p>}
          {(document || result) && (
            <div className="mt-6 grid grid-cols-1 md:grid-cols-2 gap-8">
              <div className="min-w-0">
                {state?.sourceFile ? <img ref={imageRef} alt="Documento enviado" className="w-full rounded-sm border border-line" /> :
                  <p className="text-sm text-ink/60">A imagem original não está armazenada. Consulte abaixo o texto reconhecido.</p>}
                {document && <details open={!state?.sourceFile} className="mt-4 border border-line rounded-sm p-4">
                  <summary className="cursor-pointer text-sm font-medium">Texto reconhecido pelo OCR</summary>
                  <p className="mt-2 text-xs text-ink/60">{document.ocr.model_version} · {(document.ocr.duration_ms / 1000).toLocaleString("pt-BR")} s</p>
                  <pre className="mt-3 whitespace-pre-wrap break-words text-sm font-sans">{document.ocr.content || "Nenhum texto reconhecido."}</pre>
                  {document.ocr.warnings.map((warning, index) => <p key={index} className="mt-2 text-xs text-clay">{warning}</p>)}
                </details>}
              </div>
              <div className="min-w-0">
                {result ? <ReviewFields key={documentId ?? location.key} result={result} /> : (
                  <p className="text-sm text-amber">Este registro contém apenas o OCR. A extração estruturada não foi salva. Envie novamente a imagem para executar a extração completa.</p>
                )}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}

function ReviewFields({ result }: { result: ExtractionResult }) {
  const [fields, setFields] = useState<EditableField[]>(() =>
    toDisplayFields(result).map((field) => ({ ...field, confirmed: false })),
  );
  const [finished, setFinished] = useState(false);
  const confirmedCount = fields.filter((field) => field.confirmed).length;
  const allConfirmed = confirmedCount === fields.length;

  function updateField(index: number, patch: Partial<EditableField>) {
    setFinished(false);
    setFields((prev) => prev.map((field, i) => i === index ? { ...field, ...patch } : field));
  }

  return (
    <>
      <p className="text-sm text-ink/70">OCR: {result._meta.ocr_model} · LLM: {result._meta.mapper_model} · {(result._meta.duration_ms / 1000).toLocaleString("pt-BR")} s</p>
      <p className="mt-2 text-sm text-amber">Os dados extraídos requerem revisão humana. A confiança exibida é uma estimativa heurística.</p>
      {result._warnings.length > 0 && <div role="status" className="mt-3 border border-amber/40 p-3 text-sm text-clay">
        <p className="font-medium">Avisos da extração</p>
        <ul className="mt-2 list-disc pl-4">{result._warnings.map((warning, index) => <li key={index}>{warning.field ? `${warning.field}: ` : ""}{warning.message}</li>)}</ul>
      </div>}
      <p className="mt-4 text-sm text-ink/70">{confirmedCount} de {fields.length} campos conferidos nesta sessão</p>
      <p className="mt-1 text-xs text-ink/60">Edições e confirmações abaixo são locais e não alteram os dados salvos. A API ainda não oferece gravação da revisão.</p>
      <div className="mt-3 border border-line rounded-sm px-4">
        {fields.map((field, index) => (
          <div key={field.field} className="border-b border-line last:border-b-0 pb-3">
            <FieldRow label={field.label} value={field.value} confidence={field.confidence}
              status={field.status} confirmed={field.confirmed}
              onChange={(value) => updateField(index, { value, confirmed: false })}
              onToggleConfirm={() => updateField(index, { confirmed: !field.confirmed })} />
            {(result._review[field.field].evidence.length > 0 || result._review[field.field].explanation) && (
              <details className="text-xs text-ink/60">
                <summary className="cursor-pointer">Evidências e observações</summary>
                {result._review[field.field].evidence.map((evidence, i) => (
                  <blockquote key={i} className="mt-2 border-l-2 border-line pl-2 whitespace-pre-wrap">
                    {evidence.source_excerpt}
                    {evidence.region_reference && <p className="mt-1">Região: {evidence.region_reference}</p>}
                    {evidence.bounding_box && <p className="mt-1">Área na imagem: {evidence.bounding_box.join(", ")}</p>}
                  </blockquote>
                ))}
                {result._review[field.field].explanation && <p className="mt-2">{result._review[field.field].explanation}</p>}
              </details>
            )}
          </div>
        ))}
      </div>
      <button type="button" disabled={!allConfirmed} onClick={() => setFinished(true)}
        className="mt-4 w-full py-2 rounded-sm text-sm font-medium bg-forest text-white hover:bg-forest-light disabled:bg-line disabled:text-ink/40 disabled:cursor-not-allowed">
        {finished ? "Conferência concluída nesta sessão ✓" : "Concluir conferência local"}
      </button>
    </>
  );
}

export default ReviewPage;
