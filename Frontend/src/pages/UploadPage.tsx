import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import ImageUploader from "../components/ImageUploader";
import { extractDocument } from "../api/documents";

function UploadPage() {
  const [processing, setProcessing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pending = useRef(false);
  const mounted = useRef(true);
  const navigate = useNavigate();

  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; };
  }, []);

  async function handleFileSelected(file: File) {
    if (pending.current) return;
    pending.current = true;
    setProcessing(true);
    setError(null);
    try {
      const result = await extractDocument(file);
      if (!mounted.current) return;
      navigate(result._meta.document_id ? `/documentos/${result._meta.document_id}` : "/revisao", {
        state: { result, sourceFile: file },
      });
    } catch (cause) {
      if (mounted.current) setError(cause instanceof Error ? cause.message : "Não foi possível processar o documento.");
    } finally {
      pending.current = false;
      if (mounted.current) setProcessing(false);
    }
  }

  return (
    <div className="max-w-xl">
      <h2 className="font-serif text-2xl text-ink">Novo documento</h2>
      <p className="mt-2 text-sm text-ink/70">
        Envie a foto de um auto de infração, licença ou notificação para
        extrair os dados automaticamente.
      </p>
      <div className="mt-6">
        <ImageUploader onFileSelected={handleFileSelected} disabled={processing} />
      </div>
      {processing && <p role="status" className="mt-4 text-sm text-ink/70">Processando com OCR e LLM. Isso pode levar alguns minutos...</p>}
      {error && (
        <div role="alert" className="mt-4 text-sm text-clay">
          <p>{error}</p>
          <Link to="/documentos" className="mt-2 inline-block underline">Consultar documentos salvos</Link>
        </div>
      )}
    </div>
  );
}

export default UploadPage;
