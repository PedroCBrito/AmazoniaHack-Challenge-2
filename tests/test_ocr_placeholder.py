import io

from fastapi.testclient import TestClient
from PIL import Image

from ocr_placeholder.main import app


def _png_bytes() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (1, 1), color="white").save(output, format="PNG")
    return output.getvalue()


def test_placeholder_is_live_but_not_ready() -> None:
    with TestClient(app) as client:
        live_response = client.get("/live")
        health_response = client.get("/health")

    assert live_response.status_code == 200
    assert live_response.json()["status"] == "alive"
    assert health_response.status_code == 503
    assert health_response.json()["error"]["code"] == "model_not_ready"


def test_placeholder_never_returns_fake_ocr_content() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/ocr",
            files={"image": ("document.png", _png_bytes(), "image/png")},
        )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "model_not_ready"

