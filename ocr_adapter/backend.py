import base64
import asyncio
from collections.abc import Awaitable, Callable
from html import escape
import io
from typing import Protocol

import httpx
from PIL import Image

from ocr_adapter.config import OCRSettings
from ocr_adapter.prompts import OCR_LAYOUT_PROMPT


class BackendUnavailableError(Exception):
    """The configured inference service cannot accept work."""


class BackendResponseError(Exception):
    """The inference service returned an unusable response."""


class OCRBackend(Protocol):
    """Common interface implemented by every OCR provider."""

    async def health(self) -> bool: ...

    async def recognize(self, image: bytes, content_type: str) -> str: ...


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


class TextractBackend:
    """Amazon Textract client using synchronous image-byte requests."""

    def __init__(
        self,
        settings: OCRSettings,
        client: object | None = None,
        run: Callable[..., Awaitable[dict]] | None = None,
    ) -> None:
        if client is None:
            try:
                import boto3
            except ImportError as exc:
                raise BackendUnavailableError from exc
            session = boto3.Session(
                profile_name=settings.aws_profile or None, region_name=settings.aws_region
            )
            client = session.client("textract")
        self._client = client
        self._run = run or asyncio.to_thread

    async def health(self) -> bool:
        """Report configured readiness without requiring extra IAM permissions."""
        return self._client is not None

    async def recognize(self, image: bytes, content_type: str) -> str:
        try:
            response = await self._run(
                self._client.detect_document_text,
                Document={"Bytes": image},
            )
        except Exception as exc:
            error_name = exc.__class__.__name__
            if error_name.endswith(("Error", "Exception")):
                raise BackendUnavailableError from exc
            raise BackendResponseError from exc
        try:
            with Image.open(io.BytesIO(image)) as decoded:
                return _parse_textract_content(response, decoded.width, decoded.height)
        except (OSError, ValueError) as exc:
            raise BackendResponseError from exc


def _parse_textract_content(response: object, width: int, height: int) -> str:
    if not isinstance(response, dict):
        raise BackendResponseError
    blocks = response.get("Blocks")
    if not isinstance(blocks, list):
        raise BackendResponseError
    rendered = [
        _render_textract_line(block, width, height)
        for block in blocks
        if isinstance(block, dict) and block.get("BlockType") == "LINE"
    ]
    return "\n".join(line for line in rendered if line)


def _render_textract_line(block: dict, width: int, height: int) -> str:
    text = str(block.get("Text", "")).strip()
    geometry = block.get("Geometry", {})
    box = geometry.get("BoundingBox", {}) if isinstance(geometry, dict) else {}
    left = int(round(float(box.get("Left", 0)) * 1000))
    top = int(round(float(box.get("Top", 0)) * 1000))
    right = int(round((float(box.get("Left", 0)) + float(box.get("Width", 0))) * 1000))
    bottom = int(round((float(box.get("Top", 0)) + float(box.get("Height", 0))) * 1000))
    return f'<div data-bbox="{left} {top} {right} {bottom}" data-label="Text">{escape(text)}</div>'


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
