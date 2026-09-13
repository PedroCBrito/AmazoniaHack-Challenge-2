import os
from pathlib import Path
from stat import S_IMODE

import pytest
from pydantic import ValidationError

from app.schemas.ocr import OCRRegion, OCRResult
from app.services.ocr_store import OCRStorageError, SQLiteOCRStore


pytestmark = pytest.mark.anyio


def _ocr(content: str = "AUTO DE INFRAÇÃO") -> OCRResult:
    return OCRResult(
        content=content,
        regions=[
            OCRRegion(
                id="page-1-region-0001",
                text="Número: 00831",
                page=1,
                kind="Text",
                bounding_box=[10, 20, 100, 40],
            )
        ],
        model_version="chandra-test",
        duration_ms=37,
        warnings=["layout_metadata_partial"],
    )


async def test_sqlite_store_restores_complete_ocr_after_reopen(tmp_path: Path) -> None:
    database = tmp_path / "ocr.sqlite3"
    store = SQLiteOCRStore(database)
    await store.initialize()
    if os.name != "nt":  # Windows chmod does not implement POSIX permission bits.
        assert S_IMODE(database.stat().st_mode) == 0o600
    run_id = await store.save("notice.jpg", "a" * 64, _ocr())
    await store.close()

    reopened = SQLiteOCRStore(database)
    await reopened.initialize()
    stored = await reopened.load_latest("a" * 64)
    await reopened.close()

    assert stored is not None
    assert stored.id == run_id
    assert stored.image_basename == "notice.jpg"
    assert stored.image_sha256 == "a" * 64
    assert stored.created_at.endswith("Z")
    assert stored.ocr.model_dump() == _ocr().model_dump()


async def test_sqlite_store_preserves_empty_ocr_regions(tmp_path: Path) -> None:
    empty = OCRResult(
        content="",
        regions=[],
        model_version="chandra-test",
        duration_ms=0,
        warnings=[],
    )
    store = SQLiteOCRStore(tmp_path / "ocr.sqlite3")
    await store.initialize()
    await store.save("blank.png", "b" * 64, empty)

    stored = await store.load_latest("b" * 64)
    await store.close()

    assert stored is not None
    assert stored.ocr == empty


async def test_sqlite_store_loads_newest_run_for_same_image(tmp_path: Path) -> None:
    store = SQLiteOCRStore(tmp_path / "ocr.sqlite3")
    await store.initialize()
    await store.save("notice.png", "c" * 64, _ocr("first"))
    latest_id = await store.save("notice.png", "c" * 64, _ocr("second"))

    stored = await store.load_latest("c" * 64)
    await store.close()

    assert stored is not None
    assert stored.id == latest_id
    assert stored.ocr.content == "second"


async def test_sqlite_store_rejects_invalid_source_identity(tmp_path: Path) -> None:
    store = SQLiteOCRStore(tmp_path / "ocr.sqlite3")
    await store.initialize()

    with pytest.raises(ValueError):
        await store.save("../notice.jpg", "not-a-sha256", _ocr())

    await store.close()


async def test_sqlite_store_requires_initialization(tmp_path: Path) -> None:
    store = SQLiteOCRStore(tmp_path / "ocr.sqlite3")

    with pytest.raises(OCRStorageError):
        await store.load_latest("a" * 64)


async def test_ocr_region_rejects_invalid_bounding_box() -> None:
    with pytest.raises(ValidationError):
        OCRRegion(id="r1", bounding_box=[1, 2, 3])
