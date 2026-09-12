import asyncio
import io
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Annotated

import httpx
from fastapi import FastAPI, File, Request, UploadFile
from fastapi.responses import JSONResponse
from PIL import Image, UnidentifiedImageError

from ocr_adapter.backend import (
    BackendResponseError,
    BackendUnavailableError,
    OpenAIChandraBackend,
)
from ocr_adapter.config import OCRSettings, get_settings
from ocr_adapter.errors import AdapterError, register_error_handlers
from ocr_adapter.layout import parse_regions
from ocr_adapter.schemas import (
    ErrorResponse,
    HealthResponse,
    LivenessResponse,
    OCRResult,
)


SUPPORTED_MEDIA_TYPES = {"image/jpeg": "JPEG", "image/png": "PNG"}


@dataclass(frozen=True)
class ValidatedImage:
    """Validated bytes and decoded dimensions for one image."""

    content: bytes
    content_type: str
    width: int
    height: int


class OCRService:
    """Own input validation, capacity, inference, and response shaping."""

    def __init__(
        self, settings: OCRSettings, backend: OpenAIChandraBackend
    ) -> None:
        self._settings = settings
        self._backend = backend
        self._slots = asyncio.Semaphore(settings.max_concurrent_requests)

    async def health(self) -> bool:
        """Report inference backend readiness."""
        return await self._backend.health()

    async def recognize(self, upload: UploadFile) -> OCRResult:
        try:
            await asyncio.wait_for(self._slots.acquire(), timeout=0.001)
        except TimeoutError as exc:
            raise AdapterError(
                429, "capacity_reached", "The OCR service is busy."
            ) from exc
        started = time.perf_counter()
        try:
            image = await _validate_image(upload, self._settings)
            content = await self._backend.recognize(image.content, image.content_type)
            regions, warnings = parse_regions(content, image.width, image.height)
            if not content:
                warnings.append("no_text_recognized")
            return OCRResult(
                content=content,
                regions=regions,
                model_version=self._settings.model_version,
                duration_ms=int((time.perf_counter() - started) * 1000),
                warnings=warnings,
            )
        except BackendUnavailableError as exc:
            raise AdapterError(
                503, "model_not_ready", "The OCR model is not ready."
            ) from exc
        except BackendResponseError as exc:
            raise AdapterError(500, "ocr_failed", "OCR inference failed.") from exc
        finally:
            self._slots.release()


async def _validate_image(upload: UploadFile, settings: OCRSettings) -> ValidatedImage:
    content_type = upload.content_type or ""
    if content_type not in SUPPORTED_MEDIA_TYPES:
        await upload.close()
        raise AdapterError(415, "unsupported_media_type", "Use a JPEG or PNG image.")
    content = await upload.read(settings.max_file_size_bytes + 1)
    await upload.close()
    if len(content) > settings.max_file_size_bytes:
        raise AdapterError(413, "image_too_large", "The image exceeds the size limit.")
    width, height, image_format = _decode_image(content)
    if image_format != SUPPORTED_MEDIA_TYPES[content_type]:
        raise AdapterError(415, "unsupported_media_type", "Image bytes do not match its type.")
    if width * height > settings.max_image_pixels:
        raise AdapterError(413, "image_too_large", "The image exceeds the pixel limit.")
    return ValidatedImage(content, content_type, width, height)


def _decode_image(content: bytes) -> tuple[int, int, str]:
    try:
        with Image.open(io.BytesIO(content)) as image:
            image.load()
            if image.format is None:
                raise UnidentifiedImageError
            return image.width, image.height, image.format
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise AdapterError(422, "invalid_image", "The image could not be decoded.") from exc


def create_app(
    settings: OCRSettings | None = None,
    backend: OpenAIChandraBackend | None = None,
) -> FastAPI:
    """Create the OCR adapter with an injectable inference backend."""
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        if backend is not None:
            yield
            return
        timeout = httpx.Timeout(settings.backend_timeout_seconds)
        async with httpx.AsyncClient(
            base_url=settings.normalized_backend_url, timeout=timeout
        ) as backend_http:
            application.state.ocr_service = OCRService(
                settings, OpenAIChandraBackend(backend_http, settings)
            )
            yield

    application = FastAPI(
        title="Chandra OCR Adapter",
        version="0.1.0",
        description="Private adapter for an OpenAI-compatible Chandra backend.",
        lifespan=lifespan,
    )
    if backend is not None:
        application.state.ocr_service = OCRService(settings, backend)
    register_error_handlers(application)
    _register_routes(application, settings)
    return application


def _register_routes(application: FastAPI, settings: OCRSettings) -> None:
    @application.get("/live", response_model=LivenessResponse)
    async def live() -> LivenessResponse:
        return LivenessResponse()

    @application.get(
        "/health",
        response_model=HealthResponse,
        responses={503: {"model": ErrorResponse}},
    )
    async def health(request: Request):
        if await request.app.state.ocr_service.health():
            return HealthResponse(model_version=settings.model_version)
        return JSONResponse(
            status_code=503,
            content={
                "error": {
                    "code": "model_not_ready",
                    "message": "The OCR model is not ready.",
                }
            },
        )

    @application.post(
        "/ocr", response_model=OCRResult, responses={500: {"model": ErrorResponse}}
    )
    async def recognize(
        request: Request,
        image: Annotated[UploadFile, File(description="One JPEG or PNG image")],
    ) -> OCRResult:
        return await request.app.state.ocr_service.recognize(image)


app = create_app()
