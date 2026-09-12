import io
import json

import httpx
import pytest
from PIL import Image

from ocr_adapter.backend import OpenAIChandraBackend
from ocr_adapter.config import OCRSettings
from ocr_adapter.main import create_app


pytestmark = pytest.mark.anyio


def _png_bytes(width: int = 200, height: int = 100) -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (width, height), color="white").save(output, format="PNG")
    return output.getvalue()


def _settings(**overrides: object) -> OCRSettings:
    values = {
        "backend_base_url": "http://chandra.test/v1",
        "backend_model": "chandra-ocr",
        "model_version": "chandra-ocr-2@test-revision",
        "max_file_size_bytes": 1024,
        "max_image_pixels": 50_000,
    }
    values.update(overrides)
    return OCRSettings(**values)


def _completion(content: str) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "choices": [{"message": {"content": content}}],
            "model": "chandra-ocr",
        },
    )


async def _adapter_client(handler, settings: OCRSettings | None = None):
    backend_http = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="http://chandra.test/v1/",
    )
    backend = OpenAIChandraBackend(backend_http, _settings() if settings is None else settings)
    app = create_app(settings or _settings(), backend=backend)
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://adapter.test")


async def test_health_reports_ready_when_model_is_available() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/models"
        return httpx.Response(200, json={"data": [{"id": "chandra-ocr"}]})

    async with await _adapter_client(handler) as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json()["model_version"] == "chandra-ocr-2@test-revision"


async def test_liveness_does_not_call_backend() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        raise AssertionError("liveness called the inference backend")

    async with await _adapter_client(handler) as client:
        response = await client.get("/live")

    assert response.json() == {"status": "alive", "service": "ocr-adapter"}


async def test_health_reports_unavailable_for_backend_error() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    async with await _adapter_client(handler) as client:
        response = await client.get("/health")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "model_not_ready"


async def test_ocr_calls_openai_backend_and_returns_pixel_regions() -> None:
    html = (
        '<div data-bbox="100 200 900 800" data-label="Text">'
        "Documento ambiental</div>"
    )

    async def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert request.url.path == "/v1/chat/completions"
        assert payload["model"] == "chandra-ocr"
        assert payload["messages"][0]["content"][0]["image_url"]["url"].startswith(
            "data:image/png;base64,"
        )
        return _completion(html)

    async with await _adapter_client(handler) as client:
        response = await client.post(
            "/ocr",
            files={"image": ("document.png", _png_bytes(), "image/png")},
        )

    assert response.status_code == 200
    assert response.json()["content"] == html
    assert response.json()["regions"] == [
        {
            "id": "page-1-region-0001",
            "text": "Documento ambiental",
            "page": 1,
            "kind": "Text",
            "bounding_box": [20, 20, 180, 80],
        }
    ]


async def test_ocr_sends_bearer_token_for_remote_backend() -> None:
    settings = _settings(backend_api_key="remote-secret")

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer remote-secret"
        return _completion("<div>ok</div>")

    async with await _adapter_client(handler, settings) as client:
        response = await client.post(
            "/ocr",
            files={"image": ("document.png", _png_bytes(), "image/png")},
        )

    assert response.status_code == 200


async def test_ocr_removes_backend_code_fence() -> None:
    async with await _adapter_client(
        lambda _: _completion("```html\n<div>ok</div>\n```")
    ) as client:
        response = await client.post(
            "/ocr",
            files={"image": ("document.png", _png_bytes(), "image/png")},
        )

    assert response.json()["content"] == "<div>ok</div>"


async def test_ocr_removes_backend_think_wrapper() -> None:
    async with await _adapter_client(
        lambda _: _completion("<think>\n<div>ok</div>\n</think>")
    ) as client:
        response = await client.post(
            "/ocr",
            files={"image": ("document.png", _png_bytes(), "image/png")},
        )

    assert response.json()["content"] == "<div>ok</div>"


async def test_ocr_rejects_unsupported_media_type() -> None:
    async with await _adapter_client(lambda _: _completion("unused")) as client:
        response = await client.post(
            "/ocr",
            files={"image": ("document.txt", b"plain text", "text/plain")},
        )

    assert response.status_code == 415
    assert response.json()["error"]["code"] == "unsupported_media_type"


async def test_ocr_requires_an_image() -> None:
    async with await _adapter_client(lambda _: _completion("unused")) as client:
        response = await client.post("/ocr")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_image"


async def test_ocr_rejects_corrupted_image() -> None:
    async with await _adapter_client(lambda _: _completion("unused")) as client:
        response = await client.post(
            "/ocr",
            files={"image": ("document.png", b"not an image", "image/png")},
        )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_image"


async def test_ocr_rejects_file_above_limit() -> None:
    settings = _settings(max_file_size_bytes=10)
    async with await _adapter_client(lambda _: _completion("unused"), settings) as client:
        response = await client.post(
            "/ocr",
            files={"image": ("document.png", _png_bytes(), "image/png")},
        )

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "image_too_large"


async def test_ocr_reports_backend_failure() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": "model unavailable"})

    async with await _adapter_client(handler) as client:
        response = await client.post(
            "/ocr",
            files={"image": ("document.png", _png_bytes(), "image/png")},
        )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "model_not_ready"


async def test_ocr_reports_backend_connection_failure() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection failed", request=request)

    async with await _adapter_client(handler) as client:
        response = await client.post(
            "/ocr",
            files={"image": ("document.png", _png_bytes(), "image/png")},
        )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "model_not_ready"


async def test_ocr_reports_backend_rejection() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": "bad request"})

    async with await _adapter_client(handler) as client:
        response = await client.post(
            "/ocr",
            files={"image": ("document.png", _png_bytes(), "image/png")},
        )

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "ocr_failed"


async def test_ocr_rejects_malformed_backend_response() -> None:
    async with await _adapter_client(
        lambda _: httpx.Response(200, json={"choices": []})
    ) as client:
        response = await client.post(
            "/ocr",
            files={"image": ("document.png", _png_bytes(), "image/png")},
        )

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "ocr_failed"
