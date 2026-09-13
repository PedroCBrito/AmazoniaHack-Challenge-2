"""Isolated API for browser integration tests; never connects to OCR/LLM services."""
from contextlib import asynccontextmanager

from tests.test_api import FakeOCRClient, _test_app
from tests.test_documents_api import MappedDocument


app = _test_app()
original_lifespan = app.router.lifespan_context


@asynccontextmanager
async def lifespan(application):
    async with original_lifespan(application):
        application.state.extraction_service._ocr_client = FakeOCRClient()
        application.state.extraction_service._field_mapper = MappedDocument()
        yield


app.router.lifespan_context = lifespan
