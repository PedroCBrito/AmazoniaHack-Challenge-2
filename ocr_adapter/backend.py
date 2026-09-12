import base64

import httpx

from ocr_adapter.config import OCRSettings
from ocr_adapter.prompts import OCR_LAYOUT_PROMPT


class BackendUnavailableError(Exception):
    """The configured inference service cannot accept work."""


class BackendResponseError(Exception):
    """The inference service returned an unusable response."""


class OpenAIChandraBackend:
    """OpenAI-compatible client for local or remote Chandra inference."""

    def __init__(
        self, http_client: httpx.AsyncClient, settings: OCRSettings
    ) -> None:
        self._http_client = http_client
        self._settings = settings

    async def health(self) -> bool:
        """Report whether the configured model is listed by the backend."""
        try:
            response = await self._http_client.get(
                "models", headers=self._settings.backend_headers, timeout=5.0
            )
            if not response.is_success:
                return False
            models = response.json().get("data", [])
            return any(item.get("id") == self._settings.backend_model for item in models)
        except (httpx.HTTPError, TypeError, ValueError, AttributeError):
            return False

    async def recognize(self, image: bytes, content_type: str) -> str:
        """Send one image and return Chandra's HTML response."""
        encoded = base64.b64encode(image).decode("ascii")
        payload = self._completion_payload(encoded, content_type)
        try:
            response = await self._http_client.post(
                "chat/completions",
                json=payload,
                headers=self._settings.backend_headers,
            )
        except (httpx.TimeoutException, httpx.RequestError) as exc:
            raise BackendUnavailableError from exc
        if response.status_code >= 500:
            raise BackendUnavailableError
        if not response.is_success:
            raise BackendResponseError
        return self._parse_content(response)

    def _completion_payload(self, encoded: str, content_type: str) -> dict:
        return {
            "model": self._settings.backend_model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{content_type};base64,{encoded}"
                            },
                        },
                        {"type": "text", "text": OCR_LAYOUT_PROMPT},
                    ],
                }
            ],
            "max_tokens": self._settings.max_output_tokens,
            "temperature": 0.0,
            "top_p": 0.1,
        }

    @staticmethod
    def _parse_content(response: httpx.Response) -> str:
        try:
            content = response.json()["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise BackendResponseError from exc
        if not isinstance(content, str):
            raise BackendResponseError
        return _clean_content(content)


def _clean_content(content: str) -> str:
    stripped = content.strip()
    if stripped.startswith("```") and stripped.endswith("```"):
        first_newline = stripped.find("\n")
        if first_newline != -1:
            stripped = stripped[first_newline + 1 : -3].strip()
    if stripped.startswith("<think>"):
        stripped = stripped[len("<think>") :].lstrip()
    if stripped.endswith("</think>"):
        stripped = stripped[: -len("</think>")].rstrip()
    return stripped
