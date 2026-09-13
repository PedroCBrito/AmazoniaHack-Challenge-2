import { useState } from "react";
import type { FieldStatus } from "../types/extraction";

interface FieldRowProps {
  label: string;
  value: string;
  confidence: number;
  status: FieldStatus;
  confirmed: boolean;
  onChange: (value: string) => void;
  onToggleConfirm: () => void;
}

const STATUS_LABEL: Record<FieldStatus, string> = {
  extracted: "Extraído",
  not_present: "Não presente no documento",
  explicitly_absent: "Ausente (confirmado)",
  unreadable: "Ilegível",
  ambiguous: "Ambíguo",
  not_processed: "Não processado",
};

function confidenceColor(confidence: number, status: FieldStatus): string {
  if (status === "unreadable" || status === "ambiguous") return "text-clay";
  if (status === "not_present" || status === "explicitly_absent") {
    return "text-ink/40";
  }
  if (confidence >= 0.75) return "text-forest";
  if (confidence >= 0.4) return "text-amber";
  return "text-clay";
}

function FieldRow({
  label,
  value,
  confidence,
  status,
  confirmed,
  onChange,
  onToggleConfirm,
}: FieldRowProps) {
  const [isEditing, setIsEditing] = useState(false);
  const isMissing = status === "not_present" || status === "explicitly_absent";

  return (
    <div
      className={[
        "py-3 border-b border-line last:border-b-0",
        confirmed ? "bg-forest/5 -mx-4 px-4" : "",
      ].join(" ")}
    >
      <div className="flex items-baseline justify-between gap-3">
        <span className="text-xs uppercase tracking-wide text-ink/50">
          {label}
        </span>
        <span className={`text-xs ${confidenceColor(confidence, status)}`}>
          {STATUS_LABEL[status]}
          {status === "extracted" ? ` · ${Math.round(confidence * 100)}%` : ""}
        </span>
      </div>

      <div className="mt-1 flex items-center gap-2">
        {isEditing ? (
          <textarea
            autoFocus
            aria-label={label}
            value={value}
            onChange={(e) => onChange(e.target.value)}
            onBlur={() => setIsEditing(false)}
            className="flex-1 text-sm bg-white border border-forest/40 rounded-sm px-2 py-1 outline-none focus:border-forest"
          />
        ) : (
          <button
            type="button"
            onClick={() => setIsEditing(true)}
            className={[
              "flex-1 min-w-0 whitespace-pre-wrap break-words text-left text-sm rounded-sm px-2 py-1 -mx-2 hover:bg-ink/5",
              isMissing ? "text-ink/40 italic" : "text-ink",
            ].join(" ")}
          >
            {value || "—"}
          </button>
        )}

        <button
          type="button"
          onClick={onToggleConfirm}
          aria-label={`${confirmed ? "Desmarcar revisão de" : "Marcar como revisado:"} ${label}`}
          aria-pressed={confirmed}
          title={confirmed ? "Revisado" : "Marcar como revisado"}
          className={[
            "shrink-0 w-7 h-7 rounded-full border flex items-center justify-center text-sm transition-colors",
            confirmed
              ? "bg-forest border-forest text-white"
              : "border-line text-ink/40 hover:border-forest hover:text-forest",
          ].join(" ")}
        >
          ✓
        </button>
      </div>
    </div>
  );
}

export default FieldRow;
