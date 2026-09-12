import httpx
from pydantic import ValidationError

from app.core.errors import ApplicationError
from app.schemas.ocr import OCRResult
from app.services.image_processor import PreparedImage


class ChandraClient:
    """Client for the private HTTP wrapper around Chandra."""

    def __init__(self, http_client: httpx.AsyncClient) -> None:
        self._http_client = http_client

    async def health(self) -> bool:
        try:
            response = await self._http_client.get("/health", timeout=5.0)
            return response.is_success
        except httpx.HTTPError:
            return False

    async def recognize(self, image: PreparedImage) -> OCRResult:
        try:
            response = await self._http_client.post(
                "/ocr",
                files={
                    "image": (
                        image.filename,
                        image.content,
                        image.content_type,
                    )
                },
            )
        except httpx.TimeoutException as exc:
            raise ApplicationError(
                504, "ocr_timeout", "The OCR service exceeded its deadline."
            ) from exc
        except httpx.RequestError as exc:
            raise ApplicationError(
                503, "ocr_unavailable", "The OCR service is unavailable."
            ) from exc

        if response.status_code >= 500:
            raise ApplicationError(
                503, "ocr_unavailable", "The OCR service is unavailable."
            )
        if not response.is_success:
            raise ApplicationError(
                502, "ocr_rejected_request", "The OCR service rejected the image."
            )

        try:
            return OCRResult.model_validate(response.json())
        except (ValueError, ValidationError) as exc:
            raise ApplicationError(
                502,
                "invalid_ocr_response",
                "The OCR service returned an invalid response.",
            ) from exc
