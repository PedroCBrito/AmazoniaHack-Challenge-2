import asyncio
import time

from fastapi import UploadFile

from app.core.config import Settings
from app.core.errors import ApplicationError
from app.schemas.extraction import ExtractionResult
from app.services.field_mapper import FieldMapper
from app.services.image_processor import prepare_image
from app.services.ocr_client import ChandraClient


class ExtractionService:
    def __init__(
        self,
        settings: Settings,
        ocr_client: ChandraClient,
        field_mapper: FieldMapper,
    ) -> None:
        self._settings = settings
        self._ocr_client = ocr_client
        self._field_mapper = field_mapper
        self._slots = asyncio.Semaphore(settings.max_concurrent_requests)

    async def extract(self, upload: UploadFile) -> ExtractionResult:
        try:
            await asyncio.wait_for(self._slots.acquire(), timeout=0.001)
        except TimeoutError as exc:
            raise ApplicationError(
                429, "processing_capacity_reached", "The application is busy."
            ) from exc

        started = time.perf_counter()
        try:
            async with asyncio.timeout(self._settings.processing_deadline_seconds):
                image = await prepare_image(upload, self._settings)
                ocr = await self._ocr_client.recognize(image)
                result = await self._field_mapper.map(ocr)
                result.meta.duration_ms = int((time.perf_counter() - started) * 1000)
                return result
        except TimeoutError as exc:
            raise ApplicationError(
                504,
                "processing_timeout",
                "The document processing deadline was exceeded.",
            ) from exc
        finally:
            self._slots.release()
