"""Exercise both HTTP contracts and real cleaning/mapping; only AWS is simulated."""

import io
import json
from pathlib import Path

import httpx
from PIL import Image
import pytest

from app.core.config import Settings
from app.main import create_app
from app.schemas.extraction import COMMON_FIELDS, ExtractionResult
from app.services.ocr_client import ChandraClient
from ocr_adapter.backend import TextractBackend
from ocr_adapter.config import OCRSettings
from ocr_adapter.main import create_app as create_adapter


pytestmark = pytest.mark.anyio
FIXTURES = Path(__file__).parent / "fixtures"


async def test_image_through_textract_adapter_returns_annotated_json():
    lines = (FIXTURES / "labeled_infraction.txt").read_text(encoding="utf-8").splitlines()
    expected = json.loads((FIXTURES / "labeled_infraction.expected.json").read_text(encoding="utf-8"))

    class TextractFixture:
        calls = 0

        def detect_document_text(self, *, Document):
            self.calls += 1
            with Image.open(io.BytesIO(Document["Bytes"])) as image:
                assert image.format == "PNG"
                assert image.mode == "L"
            return {"Blocks": [
                {"BlockType": "LINE", "Text": line, "Geometry": {"BoundingBox": {
                    "Left": 0.05, "Top": index / len(lines), "Width": 0.9, "Height": 0.02,
                }}} for index, line in enumerate(lines)
            ]}

    fixture = TextractFixture()
    ocr_settings = OCRSettings(provider="textract", model_version="textract-fixture")
    adapter = create_adapter(ocr_settings, TextractBackend(ocr_settings, client=fixture))
    api = create_app(Settings(_env_file=None))
    upload = io.BytesIO()
    Image.new("RGB", (200, 300), color="white").save(upload, format="JPEG")
    async with api.router.lifespan_context(api):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=adapter), base_url="http://adapter.test") as upstream:
            api.state.extraction_service._ocr_client = ChandraClient(upstream)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=api), base_url="http://api.test") as client:
                response = await client.post("/extract", files={"image": ("document.jpg", upload.getvalue(), "image/jpeg")})
    assert response.status_code == 200
    body = response.json()
    assert {key: body[key] for key in COMMON_FIELDS} == expected
    result = ExtractionResult.model_validate(body)
    assert result.meta.ocr_model == "textract-fixture"
    assert result.meta.duration_ms > 0
    assert result.review["number"].region_reference == "page-1-region-0001"
    assert len(result.review["references"].evidence) == 1
    assert fixture.calls == 1
