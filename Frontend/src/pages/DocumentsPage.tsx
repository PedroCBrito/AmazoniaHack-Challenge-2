import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { listDocuments } from "../api/documents";
import { documentTypeLabel } from "../lib/formatExtraction";
import type { DocumentList } from "../types/documents";

function DocumentsPage() {
  const [page, setPage] = useState<DocumentList | null>(null);
  const [offset, setOffset] = useState(0);
  const [attempt, setAttempt] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  function changePage(nextOffset: number) {
    setLoading(true);
    setError(null);
    setOffset(nextOffset);
    setAttempt((n) => n + 1);
  }

  useEffect(() => {
    const controller = new AbortController();
    listDocuments(offset, controller.signal).then((data) => {
      if (!controller.signal.aborted) setPage(data);
    }).catch((cause: unknown) => {
      if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : "Não foi possível carregar os documentos.");
    }).finally(() => {
      if (!controller.signal.aborted) setLoading(false);
    });
    return () => controller.abort();
  }, [offset, attempt]);

  return (
    <div className="max-w-5xl">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="font-serif text-2xl text-ink">Documentos</h2>
        <button disabled={loading} onClick={() => changePage(offset)} className="text-sm text-forest underline disabled:opacity-50">Atualizar lista</button>
      </div>
      <p className="mt-2 text-sm text-ink/70">Histórico de documentos enviados e resultados da extração.</p>
      {loading && <p role="status" className="mt-6 text-sm">Carregando documentos...</p>}
      {error && <p role="alert" className="mt-6 text-sm text-clay">{error} Use “Atualizar lista” para tentar novamente.</p>}
      {!loading && !error && page && (
        <>
          {page.total === 0 ? (
            <div className="mt-6 border border-line p-6 text-sm">
              <p>Nenhum documento enviado ainda.</p>
              <Link to="/" className="mt-3 inline-block text-forest underline">Enviar primeiro documento</Link>
            </div>
          ) : (
            <>
              <div className="mt-6 overflow-x-auto border border-line rounded-sm">
                <table className="w-full text-left text-sm">
                  <thead className="bg-forest/5"><tr>
                    <th scope="col" className="p-3">Documento</th><th scope="col" className="p-3">Enviado em</th>
                    <th scope="col" className="p-3">Município</th><th scope="col" className="p-3">Resultado</th>
                  </tr></thead>
                  <tbody>{page.items.map((doc) => (
                    <tr key={doc.id} className="border-t border-line">
                      <td className="p-3">
                        <Link className="text-forest underline break-words" to={`/documentos/${doc.id}`}>{doc.image_basename}</Link>
                        <p className="mt-1 text-xs text-ink/60">{documentTypeLabel(doc.document_type)}{doc.number ? ` · ${doc.number}` : ""}</p>
                      </td>
                      <td className="p-3">{new Date(doc.created_at).toLocaleString("pt-BR")}</td>
                      <td className="p-3">{doc.municipality ?? "—"}</td>
                      <td className="p-3">{doc.status === "extracted" ? "Extração salva · requer revisão" : "OCR salvo · sem extração estruturada"}</td>
                    </tr>
                  ))}</tbody>
                </table>
              </div>
              <div className="mt-4 flex items-center justify-between gap-3 text-sm">
                <button disabled={offset === 0} onClick={() => changePage(Math.max(0, offset - page.limit))} className="text-forest underline disabled:opacity-40">Anterior</button>
                <span>{page.items.length ? `${offset + 1}–${offset + page.items.length}` : "0"} de {page.total} documentos</span>
                <button disabled={offset + page.limit >= page.total} onClick={() => changePage(offset + page.limit)} className="text-forest underline disabled:opacity-40">Próxima</button>
              </div>
            </>
          )}
        </>
      )}
    </div>
  );
}

export default DocumentsPage;
