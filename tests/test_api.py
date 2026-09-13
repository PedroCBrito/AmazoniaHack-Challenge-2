import asyncio
import io
import threading
from contextlib import asynccontextmanager
from email import policy
from email.parser import BytesParser

import cv2
import httpx
import pytest
from PIL import Image

from app.core.config import Settings
from app.core.errors import ApplicationError
from app.main import create_app
from app.schemas.ocr import OCRResult
from app.services.image_cleaner import clean_image
from app.services.ocr_client import ChandraClient


pytestmark = pytest.mark.anyio


def _png_bytes() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (1, 1), color="white").save(output, format="PNG")
    return output.getvalue()


PNG_BYTES = _png_bytes()


class FakeOCRClient:
    async def health(self) -> bool:
        return True

    async def recognize(self, _image: object) -> OCRResult:
        return OCRResult(
            content="AUTO DE INFRAÇÃO Nº 000123/2026",
            regions=[],
            model_version="test-chandra",
            duration_ms=10,
            warnings=[],
        )


class UnavailableOCRClient(FakeOCRClient):
    async def recognize(self, _image: object) -> OCRResult:
        raise ApplicationError(503, "ocr_unavailable", "The OCR service is unavailable.")


def _test_app():
    return create_app(
        Settings(
            environment="test",
            chandra_base_url="http://ocr.test",
            max_file_size_bytes=1024,
            max_image_pixels=100,
        )
    )


@asynccontextmanager
async def _request_client(app):
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://api.test"
        ) as client:
            yield client


async def test_health_reports_ready_dependency() -> None:
    app = _test_app()
    async with _request_client(app) as client:
        app.state.ocr_client = FakeOCRClient()
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "ready",
        "dependencies": {"ocr": "ready"},
    }


async def test_liveness_does_not_call_dependencies() -> None:
    app = _test_app()
    async with _request_client(app) as client:
        response = await client.get("/live")

    assert response.status_code == 200
    assert response.json() == {"status": "alive", "service": "api"}


async def test_extract_returns_complete_review_contract() -> None:
    app = _test_app()
    async with _request_client(app) as client:
        app.state.extraction_service._ocr_client = FakeOCRClient()
        response = await client.post(
            "/extract", files={"image": ("document.png", PNG_BYTES, "image/png")}
        )

    assert response.status_code == 200
    body = response.json()
    assert body["number"] is None
    assert body["_meta"]["review_required"] is True
    assert body["_meta"]["ocr_model"] == "test-chandra"
    assert body["_review"]["number"]["status"] == "not_processed"
    assert body["confidence"]["number"] == 0.0
    assert body["_warnings"][0]["code"] == "field_mapping_not_configured"


async def test_extract_rejects_unsupported_media_type() -> None:
    app = _test_app()
    async with _request_client(app) as client:
        response = await client.post(
            "/extract", files={"image": ("document.txt", b"not an image", "text/plain")}
        )

    assert response.status_code == 415
    assert response.json()["error"]["code"] == "unsupported_media_type"


async def test_extract_rejects_corrupted_image() -> None:
    app = _test_app()
    async with _request_client(app) as client:
        response = await client.post(
            "/extract",
            files={"image": ("document.png", b"not an image", "image/png")},
        )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_image"


async def test_extract_rejects_mismatched_media_type() -> None:
    app = _test_app()
    async with _request_client(app) as client:
        response = await client.post(
            "/extract", files={"image": ("document.jpg", PNG_BYTES, "image/jpeg")}
        )

    assert response.status_code == 415
    assert response.json()["error"]["code"] == "media_type_mismatch"


async def test_dependency_failure_is_not_returned_as_empty_success() -> None:
    app = _test_app()
    async with _request_client(app) as client:
        app.state.extraction_service._ocr_client = UnavailableOCRClient()
        response = await client.post(
            "/extract", files={"image": ("document.png", PNG_BYTES, "image/png")}
        )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "ocr_unavailable"


@pytest.mark.parametrize("enabled", [True, False])
async def test_extract_sends_prepared_image_over_ocr_http_contract(enabled) -> None:
    output = io.BytesIO()
    Image.new("RGB", (60, 40), (200, 180, 150)).save(output, format="JPEG")
    calls = []

    def handle_ocr(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        assert request.url.path == "/ocr"
        envelope = (
            f"Content-Type: {request.headers['content-type']}\r\nMIME-Version: 1.0\r\n\r\n"
        ).encode() + request.content
        part = list(BytesParser(policy=policy.default).parsebytes(envelope).iter_parts())[0]
        assert part.get_param("name", header="content-disposition") == "image"
        assert part.get_content_type() == ("image/png" if enabled else "image/jpeg")
        assert part.get_filename() == ("document.png" if enabled else "document.jpeg")
        with Image.open(io.BytesIO(part.get_payload(decode=True))) as image:
            assert image.size == (60, 40)
            assert image.mode == ("L" if enabled else "RGB")
            assert (image.convert("L").getpixel((0, 0)) > 250) == enabled
        return httpx.Response(200, json={
            "content": "AUTO 123", "regions": [], "model_version": "test",
            "duration_ms": 1, "warnings": [],
        })

    app = create_app(Settings(_env_file=None, image_cleaning_enabled=enabled))
    async with httpx.AsyncClient(
        base_url="http://ocr.test", transport=httpx.MockTransport(handle_ocr)
    ) as upstream, _request_client(app) as client:
        app.state.extraction_service._ocr_client = ChandraClient(upstream)
        response = await client.post(
            "/extract", files={"image": ("original.jpg", output.getvalue(), "image/jpeg")}
        )
    assert response.status_code == 200
    assert len(calls) == 1


async def test_cleaning_failure_returns_error_without_calling_ocr(monkeypatch) -> None:
    def failing_cleaner(_image):
        raise cv2.error("private details")

    class UnexpectedOCRClient(FakeOCRClient):
        async def recognize(self, _image):
            pytest.fail("OCR must not run after cleaning failure")

    monkeypatch.setattr("app.services.image_processor.clean_image", failing_cleaner)
    app = _test_app()
    async with _request_client(app) as client:
        app.state.extraction_service._ocr_client = UnexpectedOCRClient()
        response = await client.post(
            "/extract", files={"image": ("document.png", PNG_BYTES, "image/png")}
        )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "image_cleaning_failed"
    assert "private details" not in response.text


async def test_cleaning_keeps_event_loop_responsive_and_holds_capacity_after_timeout(monkeypatch) -> None:
    started = threading.Event()
    release = threading.Event()

    def blocked_cleaner(image):
        started.set()
        if not release.wait(timeout=5):
            raise RuntimeError("Test did not release the cleaner")
        return clean_image(image)

    class RecordingOCRClient(FakeOCRClient):
        calls = 0

        async def recognize(self, image):
            self.calls += 1
            return await super().recognize(image)

    monkeypatch.setattr("app.services.image_processor.clean_image", blocked_cleaner)
    app = create_app(Settings(_env_file=None, processing_deadline_seconds=0.1))
    ocr = RecordingOCRClient()
    async with _request_client(app) as client:
        app.state.extraction_service._ocr_client = ocr
        first = asyncio.create_task(client.post(
            "/extract", files={"image": ("document.png", PNG_BYTES, "image/png")}
        ))
        try:
            assert await asyncio.to_thread(started.wait, 2)
            live = await client.get("/live")
            assert live.status_code == 200
            await asyncio.sleep(0.15)  # Let the request deadline expire.
            assert not first.done()  # Native worker still owns its capacity slot.
            second = await client.post(
                "/extract", files={"image": ("document.png", PNG_BYTES, "image/png")}
            )
            assert second.status_code == 429
        finally:
            release.set()
            response = await asyncio.wait_for(first, timeout=3)
        assert response.status_code == 504
        assert response.json()["error"]["code"] == "processing_timeout"
        assert ocr.calls == 0
        # Capacity is restored once the timed-out worker has actually finished.
        third = await client.post(
            "/extract", files={"image": ("document.png", PNG_BYTES, "image/png")}
        )
        assert third.status_code == 200
        assert ocr.calls == 1
