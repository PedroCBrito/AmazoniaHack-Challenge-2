import io
import json
from pathlib import Path

import httpx
from PIL import Image
import pytest

from app.core.config import Settings
from app.main import create_app
from app.schemas.extraction import ExtractionResult
from app.services.ocr_client import ChandraClient
from scripts.diagnose_extraction import diagnose


pytestmark = pytest.mark.anyio
FIXTURES = Path(__file__).parent / "fixtures"


async def test_extract_route_uses_the_corrected_mapper_with_captured_ocr():
    captured = json.loads((FIXTURES / "infraction-image.ocr.json").read_text(encoding="utf-8"))
    expected = json.loads((FIXTURES / "infraction-image.expected.json").read_text(encoding="utf-8"))
    image = io.BytesIO()
    Image.new("RGB", (1024, 1536), "white").save(image, format="JPEG")
    app = create_app(Settings(_env_file=None))

    def ocr_response(request):
        assert request.url.path == "/ocr"
        assert b"image/png" in request.content  # Actual application cleaning ran.
        return httpx.Response(200, json=captured)

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(base_url="http://ocr.test", transport=httpx.MockTransport(ocr_response)) as upstream:
            app.state.extraction_service._ocr_client = ChandraClient(upstream)
            async with httpx.AsyncClient(base_url="http://api.test", transport=httpx.ASGITransport(app=app)) as client:
                response = await client.post("/extract", files={"image": ("document.jpg", image.getvalue(), "image/jpeg")})
    assert response.status_code == 200
    body = response.json()
    assert {name: body[name] for name in expected} == expected
    result = ExtractionResult.model_validate(body)
    assert result.meta.mapper_model == "portuguese-form-rules-v2"
    assert result.meta.review_required


async def test_diagnostic_replays_saved_ocr_without_inference_or_overwrites(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Saved OCR replay must not call inference")

    monkeypatch.setattr(httpx, "AsyncClient", forbidden)
    output = tmp_path / "diagnostic"
    await diagnose(FIXTURES / "infraction-image.ocr.json", output, True, "http://unused.test")
    body = json.loads((output / "mapped.json").read_text(encoding="utf-8"))
    assert body["number"] == "00092"
    assert body["fine_brl"] == 117093.5
    with pytest.raises(ValueError, match="new output directory"):
        await diagnose(FIXTURES / "infraction-image.ocr.json", output, True, "http://unused.test")
