import json

import httpx
from pydantic import ValidationError
import pytest

from app.schemas.ocr import OCRResult
from app.services.field_mapper import RuleBasedFieldMapper
from scripts.export_json import export_images


pytestmark = pytest.mark.anyio


async def test_export_preserves_basename_unicode_and_aliases(tmp_path):
    result = await RuleBasedFieldMapper().map(OCRResult(
        content="AUTO DE INFRAÇÃO Nº 00831/2026\nMunicípio: Belém", model_version="fixture", duration_ms=0,
    ))
    image = tmp_path / "03-auto-de-infracao-00831.jpg"
    image.write_bytes(b"image-fixture")

    def handle(request):
        assert request.url.path == "/extract"
        assert b'name="image"' in request.content
        return httpx.Response(200, json=result.model_dump(mode="json", by_alias=True))

    with httpx.Client(base_url="http://api.test", transport=httpx.MockTransport(handle)) as client:
        written = export_images([image], tmp_path / "outputs", client)
    assert written[0].name == "03-auto-de-infracao-00831.json"
    text = written[0].read_text(encoding="utf-8")
    assert "Belém" in text
    body = json.loads(text)
    assert body["number"] == "00831"
    assert "_meta" in body and "meta" not in body


@pytest.mark.parametrize("response", [httpx.Response(503, json={"error": {"code": "ocr_unavailable"}}), httpx.Response(200, json={"number": "00831"})])
async def test_api_failure_or_invalid_schema_is_not_saved(tmp_path, response):
    image = tmp_path / "document.png"
    image.write_bytes(b"fixture")
    output = tmp_path / "outputs"
    with httpx.Client(base_url="http://api.test", transport=httpx.MockTransport(lambda _: response)) as client:
        with pytest.raises((httpx.HTTPStatusError, ValidationError)):
            export_images([image], output, client)
    assert list(output.iterdir()) == []


async def test_existing_output_and_basename_collision_fail_before_network(tmp_path):
    first, second = tmp_path / "document.jpg", tmp_path / "document.png"
    first.write_bytes(b"fixture")
    second.write_bytes(b"fixture")
    output = tmp_path / "outputs"

    def unexpected(_):
        pytest.fail("Preflight must prevent the API call")

    with httpx.Client(base_url="http://api.test", transport=httpx.MockTransport(unexpected)) as client:
        with pytest.raises(ValueError, match="conflicting"):
            export_images([first, second], output, client)
        output.mkdir()
        existing = output / "document.json"
        existing.write_text("previous result", encoding="utf-8")
        with pytest.raises(FileExistsError):
            export_images([first], output, client)
    assert existing.read_text(encoding="utf-8") == "previous result"
