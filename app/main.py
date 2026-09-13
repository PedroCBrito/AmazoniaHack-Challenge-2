from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager

import httpx
from fastapi import FastAPI

from app.api.routes import router
from app.core.config import Settings, get_settings
from app.core.errors import register_error_handlers
from app.services.extraction import ExtractionService
from app.services.field_mapper import FieldMapper, LlamaCppFieldMapper
from app.services.ocr_client import ChandraClient


def create_app(
    settings: Settings | None = None,
    field_mapper: FieldMapper | None = None,
) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        async with AsyncExitStack() as stack:
            ocr_http = await stack.enter_async_context(httpx.AsyncClient(
                base_url=str(settings.chandra_base_url).rstrip("/"),
                timeout=httpx.Timeout(settings.chandra_timeout_seconds),
            ))
            active_mapper = field_mapper
            if active_mapper is None:
                mapper_http = await stack.enter_async_context(httpx.AsyncClient(
                    base_url=str(settings.mapper_base_url).rstrip("/") + "/",
                    timeout=httpx.Timeout(settings.mapper_timeout_seconds),
                ))
                active_mapper = LlamaCppFieldMapper(
                    mapper_http,
                    settings.mapper_model,
                    settings.mapper_max_output_tokens,
                )
            ocr_client = ChandraClient(ocr_http)
            app.state.ocr_client = ocr_client
            app.state.extraction_service = ExtractionService(
                settings=settings,
                ocr_client=ocr_client,
                field_mapper=active_mapper,
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
