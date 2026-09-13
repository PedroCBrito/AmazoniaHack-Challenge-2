import sqlite3

import pytest

from app.core.errors import ApplicationError
from app.schemas.extraction import DocumentType, Evidence, FieldReview, FieldStatus
from app.services.ocr_store import OCRStorageError, SQLiteOCRStore
from tests.test_api import FakeOCRClient, PNG_BYTES, _request_client, _test_app
from tests.test_extraction_schema import _result


pytestmark = pytest.mark.anyio


class MappedDocument:
    async def map(self, _ocr):
        result = _result()
        values = {
            "document_type": DocumentType.INFRACTION_NOTICE, "number": "000123",
            "municipality": "Belém", "coordinates": ["1°S", "48°W"],
            "fields": {"Observações": "Vegetação nativa"},
        }
        for field, value in values.items():
            setattr(result, field, value)
            setattr(result.confidence, field, 0.8)
            result.review[field] = FieldReview(
                status=FieldStatus.EXTRACTED,
                evidence=[Evidence(source_excerpt=str(value), region_reference="r1")],
            )
        return result


async def test_upload_list_and_detail_survive_restart(tmp_path):
    database = tmp_path / "documents.sqlite3"
    app = _test_app(database_path=database)
    async with _request_client(app) as client:
        assert (await client.get("/documents")).json() == {
            "items": [], "total": 0, "limit": 20, "offset": 0,
        }
        app.state.extraction_service._ocr_client = FakeOCRClient()
        app.state.extraction_service._field_mapper = MappedDocument()
        response = await client.post(
            "/extract", files={"image": ("autuação.png", PNG_BYTES, "image/png")}
        )
        assert response.status_code == 200
        extracted = response.json()
        document_id = extracted["_meta"]["document_id"]

    reopened = _test_app(database_path=database)
    async with _request_client(reopened) as client:
        listing = (await client.get("/documents")).json()
        assert listing["total"] == 1
        item = listing["items"][0]
        assert item["id"] == document_id
        assert item["status"] == "extracted"
        assert item["number"] == "000123"
        assert item["municipality"] == "Belém"
        assert item["image_basename"] == "autuação.png"
        detail = (await client.get(f"/documents/{document_id}")).json()
        assert detail["extraction"] == extracted
        assert detail["ocr"]["content"] == "AUTO DE INFRAÇÃO Nº 000123/2026"


async def test_history_includes_legacy_ocr_with_pagination(tmp_path):
    database = tmp_path / "legacy.sqlite3"
    store = SQLiteOCRStore(database)
    await store.initialize()
    ocr = await FakeOCRClient().recognize(None)
    await store.save("older.png", "a" * 64, ocr)
    newest = await store.save("newer.png", "b" * 64, ocr)
    await store.close()
    # Simulate a database from before extraction persistence was introduced.
    with sqlite3.connect(database) as connection:
        connection.execute("DROP TABLE document_extractions")

    async with _request_client(_test_app(database_path=database)) as client:
        first = (await client.get("/documents?limit=1")).json()
        second = (await client.get("/documents?limit=1&offset=1")).json()
        assert first["total"] == second["total"] == 2
        assert first["items"][0]["id"] == newest
        assert second["items"][0]["image_basename"] == "older.png"
        assert first["items"][0]["status"] == "ocr_only"
        detail = (await client.get(f"/documents/{newest}")).json()
        assert detail["extraction"] is None
        assert detail["ocr"]["content"] == ocr.content
        assert (await client.get("/documents?offset=100")).json()["items"] == []


@pytest.mark.parametrize("path,status", [
    ("/documents/999", 404), ("/documents/0", 422),
    ("/documents/no-id", 422), ("/documents?limit=0", 422),
    ("/documents?limit=101", 422), ("/documents?offset=-1", 422),
])
async def test_invalid_document_queries(path, status):
    async with _request_client(_test_app()) as client:
        response = await client.get(path)
        assert response.status_code == status
        assert "error" in response.json()


async def test_mapper_failure_keeps_ocr_available():
    class FailingMapper:
        async def map(self, _ocr):
            raise ApplicationError(503, "mapper_unavailable", "Mapper unavailable")

    app = _test_app()
    async with _request_client(app) as client:
        app.state.extraction_service._ocr_client = FakeOCRClient()
        app.state.extraction_service._field_mapper = FailingMapper()
        response = await client.post(
            "/extract", files={"image": ("notice.png", PNG_BYTES, "image/png")}
        )
        assert response.status_code == 503
        item = (await client.get("/documents")).json()["items"][0]
        assert item["status"] == "ocr_only"
        assert (await client.get(f"/documents/{item['id']}")).json()["extraction"] is None


async def test_extraction_storage_failure_is_reported_without_losing_ocr(monkeypatch):
    async def fail(*_args):
        raise OCRStorageError("private database details")

    app = _test_app()
    async with _request_client(app) as client:
        app.state.extraction_service._ocr_client = FakeOCRClient()
        monkeypatch.setattr(app.state.ocr_store, "save_extraction", fail)
        response = await client.post(
            "/extract", files={"image": ("notice.png", PNG_BYTES, "image/png")}
        )
        assert response.status_code == 500
        assert response.json()["error"]["code"] == "extraction_storage_failed"
        assert "private" not in response.text
        assert (await client.get("/documents")).json()["items"][0]["status"] == "ocr_only"


async def test_history_storage_failure_returns_safe_error(monkeypatch):
    async def fail(*_args):
        raise OCRStorageError("private database details")

    app = _test_app()
    async with _request_client(app) as client:
        monkeypatch.setattr(app.state.ocr_store, "list_documents", fail)
        monkeypatch.setattr(app.state.ocr_store, "get_document", fail)
        for path in ["/documents", "/documents/1"]:
            response = await client.get(path)
            assert response.status_code == 500
            assert response.json()["error"]["code"] == "document_storage_failed"
            assert "private" not in response.text
