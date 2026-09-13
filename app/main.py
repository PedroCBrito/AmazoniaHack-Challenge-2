from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI

from app.api.routes import router
from app.core.config import Settings, get_settings
from app.core.errors import register_error_handlers
from app.services.extraction import ExtractionService
from app.services.field_mapper import FieldMapper, RuleBasedFieldMapper
from app.services.ocr_client import ChandraClient


def create_app(settings: Settings | None = None, field_mapper: FieldMapper | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        timeout = httpx.Timeout(settings.chandra_timeout_seconds)
        async with httpx.AsyncClient(
            base_url=str(settings.chandra_base_url).rstrip("/"),
            timeout=timeout,
        ) as http_client:
            ocr_client = ChandraClient(http_client)
            app.state.ocr_client = ocr_client
            app.state.extraction_service = ExtractionService(
                settings=settings,
                ocr_client=ocr_client,
                field_mapper=field_mapper if field_mapper is not None else RuleBasedFieldMapper(),
            )
            yield

    app = FastAPI(
        title=settings.name,
        version="0.1.0",
        description=(
            "Receives one environmental document image, delegates OCR to a "
            "private Chandra service, and returns a review-oriented JSON contract."
        ),
        lifespan=lifespan,
    )
    register_error_handlers(app)
    app.include_router(router)
    return app


app = create_app()

