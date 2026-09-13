import { useCallback, useEffect, useRef, useState } from "react";

const ACCEPTED_TYPES = ["image/jpeg", "image/png"];
const MAX_SIZE_MB = 15;

interface ImageUploaderProps {
  onFileSelected: (file: File) => void;
  disabled?: boolean;
}

function validateFile(file: File): string | null {
  if (!ACCEPTED_TYPES.includes(file.type)) {
    return "Formato não suportado. Envie uma foto em JPG ou PNG.";
  }
  if (file.size === 0) return "O arquivo está vazio. Selecione outra imagem.";
  if (file.size > MAX_SIZE_MB * 1024 * 1024) {
    return `Arquivo muito grande. O limite é ${MAX_SIZE_MB}MB.`;
  }
  return null;
}

function ImageUploader({ onFileSelected, disabled }: ImageUploaderProps) {
  const [preview, setPreview] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => () => { if (preview) URL.revokeObjectURL(preview); }, [preview]);

  const handleFile = useCallback(
    (file: File) => {
      if (disabled) return;
      const validationError = validateFile(file);
      if (validationError) {
        setError(validationError);
        setPreview(null);
        return;
      }
      setError(null);
      setPreview(URL.createObjectURL(file));
      onFileSelected(file);
    },
    [onFileSelected, disabled],
  );

  return (
    <div>
      <div
        role="button"
        aria-disabled={disabled}
        tabIndex={disabled ? -1 : 0}
        onClick={() => !disabled && inputRef.current?.click()}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            if (!disabled) inputRef.current?.click();
          }
        }}
        onDragOver={(e) => {
          e.preventDefault();
          if (!disabled) setIsDragging(true);
        }}
        onDragLeave={() => setIsDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setIsDragging(false);
          if (disabled) return;
          const file = e.dataTransfer.files?.[0];
          if (file) handleFile(file);
        }}
        className={[
          "border-2 border-dashed rounded-sm p-8 text-center cursor-pointer transition-colors",
          isDragging ? "border-forest bg-forest/5" : "border-line",
          disabled ? "opacity-50 cursor-not-allowed" : "",
        ].join(" ")}
      >
        {preview ? (
          <img src={preview} alt="Pré-visualização do documento" className="max-h-64 mx-auto rounded-sm" />
        ) : (
          <div className="text-sm text-ink/70">
            <p className="font-medium text-ink">Arraste a foto do documento aqui</p>
            <p className="mt-1">ou clique para selecionar um arquivo</p>
            <p className="mt-3 text-xs text-ink/50">JPG ou PNG · até {MAX_SIZE_MB}MB</p>
          </div>
        )}
      </div>

      <input
        ref={inputRef}
        type="file"
        accept={ACCEPTED_TYPES.join(",")}
        className="hidden"
        disabled={disabled}
        onChange={(e) => {
          const file = e.target.files?.[0];
          e.target.value = "";
          if (file) handleFile(file);
        }}
      />

      {error && <p role="alert" className="mt-2 text-sm text-clay">{error}</p>}
    </div>
  );
}

export default ImageUploader;
