import io

from fastapi.testclient import TestClient
from PIL import Image

from app.core.config import Settings
from app.core.errors import ApplicationError
from app.main import create_app
from app.schemas.ocr import OCRResult


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


def test_health_reports_ready_dependency() -> None:
    app = _test_app()
    with TestClient(app) as client:
        app.state.ocr_client = FakeOCRClient()
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "ready",
        "dependencies": {"ocr": "ready"},
    }


def test_liveness_does_not_call_dependencies() -> None:
    app = _test_app()
    with TestClient(app) as client:
        response = client.get("/live")

    assert response.status_code == 200
    assert response.json() == {"status": "alive", "service": "api"}


def test_extract_returns_complete_review_contract() -> None:
    app = _test_app()
    with TestClient(app) as client:
        app.state.extraction_service._ocr_client = FakeOCRClient()
        response = client.post(
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


def test_extract_rejects_unsupported_media_type() -> None:
    app = _test_app()
    with TestClient(app) as client:
        response = client.post(
            "/extract", files={"image": ("document.txt", b"not an image", "text/plain")}
        )

    assert response.status_code == 415
    assert response.json()["error"]["code"] == "unsupported_media_type"


def test_extract_rejects_corrupted_image() -> None:
    app = _test_app()
    with TestClient(app) as client:
        response = client.post(
            "/extract",
            files={"image": ("document.png", b"not an image", "image/png")},
        )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_image"


def test_extract_rejects_mismatched_media_type() -> None:
    app = _test_app()
    with TestClient(app) as client:
        response = client.post(
            "/extract", files={"image": ("document.jpg", PNG_BYTES, "image/jpeg")}
        )

    assert response.status_code == 415
    assert response.json()["error"]["code"] == "media_type_mismatch"


def test_dependency_failure_is_not_returned_as_empty_success() -> None:
    app = _test_app()
    with TestClient(app) as client:
        app.state.extraction_service._ocr_client = UnavailableOCRClient()
        response = client.post(
            "/extract", files={"image": ("document.png", PNG_BYTES, "image/png")}
        )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "ocr_unavailable"
