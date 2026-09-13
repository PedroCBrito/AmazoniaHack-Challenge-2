const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || "/api").replace(/\/$/, "");


export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, init);
  } catch (error) {
    if (init?.signal?.aborted) throw error;
    throw new ApiError("Não foi possível conectar à API. Verifique se o serviço está rodando.", 0);
  }

  if (!response.ok) {
    const body = await response.json().catch(() => null);
    const messages: Record<number, string> = {
      404: "Documento não encontrado.",
      413: "A imagem excede o limite de tamanho permitido pela API.",
      415: "Formato não suportado. Envie uma imagem JPEG ou PNG.",
      422: "A imagem ou os dados enviados são inválidos.",
      429: "O serviço está processando outro documento. Tente novamente em instantes.",
      502: "O OCR ou a LLM retornou uma resposta inválida.",
      503: "O serviço de OCR ou a LLM está indisponível.",
      504: "O processamento excedeu o tempo limite. Consulte o histórico antes de reenviar.",
    };
    throw new ApiError(messages[response.status] ?? body?.error?.message ?? "Não foi possível concluir a solicitação.", response.status);
  }

  try {
    return await response.json() as T;
  } catch {
    throw new ApiError("A API retornou uma resposta inválida. Verifique a configuração de conexão.", response.status);
  }
}

export const api = {
  get: <T>(path: string, signal?: AbortSignal) => request<T>(path, { signal }),

  postJson: <T>(path: string, body: unknown) =>
    request<T>(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),

  postFile: <T>(path: string, file: File, fieldName = "image") => {
    const formData = new FormData();
    formData.append(fieldName, file);
    return request<T>(path, { method: "POST", body: formData });
  },
};
