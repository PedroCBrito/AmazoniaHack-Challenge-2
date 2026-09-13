import asyncio
import json
import os
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from pydantic import ValidationError

from app.schemas.ocr import OCRRegion, OCRResult
from app.schemas.extraction import ExtractionResult
from app.schemas.documents import DocumentDetail, DocumentList, DocumentSummary


SCHEMA = """
CREATE TABLE IF NOT EXISTS ocr_runs (
    id INTEGER PRIMARY KEY,
    image_basename TEXT NOT NULL,
    image_sha256 TEXT NOT NULL,
    raw_text TEXT NOT NULL,
    model_version TEXT NOT NULL,
    duration_ms INTEGER NOT NULL CHECK (duration_ms >= 0),
    warnings_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
CREATE INDEX IF NOT EXISTS ocr_runs_image_sha256_idx
    ON ocr_runs (image_sha256, id DESC);
CREATE TABLE IF NOT EXISTS ocr_regions (
    run_id INTEGER NOT NULL REFERENCES ocr_runs(id) ON DELETE CASCADE,
    ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
    region_id TEXT NOT NULL,
    text TEXT,
    page INTEGER CHECK (page IS NULL OR page >= 1),
    kind TEXT,
    bounding_box_json TEXT,
    PRIMARY KEY (run_id, ordinal)
);
CREATE TABLE IF NOT EXISTS document_extractions (
    run_id INTEGER PRIMARY KEY REFERENCES ocr_runs(id) ON DELETE CASCADE,
    result_json TEXT NOT NULL
);
"""


class OCRStorageError(Exception):
    """Report an OCR persistence failure without exposing stored content."""


class OCRStore(Protocol):
    """Persist OCR output before downstream field mapping."""

    async def save(
        self, image_basename: str, image_sha256: str, ocr: OCRResult
    ) -> int: ...

    async def save_extraction(self, run_id: int, result: ExtractionResult) -> None: ...

    async def list_documents(self, limit: int, offset: int) -> DocumentList: ...

    async def get_document(self, run_id: int) -> DocumentDetail | None: ...


@dataclass(frozen=True, slots=True)
class StoredOCRRun:
    """One persisted OCR run and its reconstructed OCR result."""

    id: int
    image_basename: str
    image_sha256: str
    created_at: str
    ocr: OCRResult


class SQLiteOCRStore:
    """Store OCR runs in one local SQLite database."""

    def __init__(self, database_path: str | Path) -> None:
        self._database_path = Path(database_path)
        self._connection: sqlite3.Connection | None = None
        self._lock = asyncio.Lock()

    async def initialize(self) -> None:
        """Open the database and create the current schema."""
        async with self._lock:
            if self._connection is not None:
                return
            try:
                self._connection = await asyncio.to_thread(self._open_database)
            except (OSError, sqlite3.Error) as exc:
                raise OCRStorageError("Could not initialize OCR storage") from exc

    async def close(self) -> None:
        """Close the database connection."""
        async with self._lock:
            connection, self._connection = self._connection, None
            if connection is not None:
                await asyncio.to_thread(connection.close)

    async def save(
        self, image_basename: str, image_sha256: str, ocr: OCRResult
    ) -> int:
        """Persist one OCR result and return its run ID."""
        _validate_source_identity(image_basename, image_sha256)
        async with self._lock:
            try:
                return await asyncio.to_thread(
                    self._save, image_basename, image_sha256, ocr
                )
            except (OSError, sqlite3.Error) as exc:
                raise OCRStorageError("Could not persist OCR output") from exc

    async def load_latest(self, image_sha256: str) -> StoredOCRRun | None:
        """Load the newest OCR run for one original image hash."""
        _validate_sha256(image_sha256)
        async with self._lock:
            try:
                return await asyncio.to_thread(self._load_latest, image_sha256)
            except (
                json.JSONDecodeError,
                OSError,
                sqlite3.Error,
                TypeError,
                ValidationError,
                ValueError,
            ) as exc:
                raise OCRStorageError("Could not load OCR output") from exc

    async def save_extraction(self, run_id: int, result: ExtractionResult) -> None:
        async with self._lock:
            try:
                await asyncio.to_thread(
                    self._save_extraction, run_id, result.model_dump_json(by_alias=True)
                )
            except sqlite3.Error as exc:
                raise OCRStorageError("Could not persist extraction") from exc

    def _save_extraction(self, run_id: int, result_json: str) -> None:
        connection = self._require_connection()
        with connection:
            connection.execute(
                "INSERT INTO document_extractions (run_id, result_json) VALUES (?, ?)",
                (run_id, result_json),
            )

    async def list_documents(self, limit: int, offset: int) -> DocumentList:
        async with self._lock:
            try:
                return await asyncio.to_thread(self._list_documents, limit, offset)
            except (sqlite3.Error, ValueError, TypeError) as exc:
                raise OCRStorageError("Could not list documents") from exc

    def _list_documents(self, limit: int, offset: int) -> DocumentList:
        connection = self._require_connection()
        rows = connection.execute(
            """SELECT r.id, r.image_basename, r.created_at, r.model_version,
                      e.run_id AS extraction_id,
                      json_extract(e.result_json, '$.document_type') AS document_type,
                      json_extract(e.result_json, '$.number') AS number,
                      json_extract(e.result_json, '$.municipality') AS municipality
               FROM ocr_runs r LEFT JOIN document_extractions e ON e.run_id = r.id
               ORDER BY r.id DESC LIMIT ? OFFSET ?""", (limit, offset)
        ).fetchall()
        total = connection.execute("SELECT COUNT(*) FROM ocr_runs").fetchone()[0]
        return DocumentList(
            items=[DocumentSummary(
                id=row["id"], image_basename=row["image_basename"],
                created_at=row["created_at"], ocr_model=row["model_version"],
                status="extracted" if row["extraction_id"] is not None else "ocr_only",
                document_type=row["document_type"], number=row["number"],
                municipality=row["municipality"],
            ) for row in rows],
            total=total, limit=limit, offset=offset,
        )

    async def get_document(self, run_id: int) -> DocumentDetail | None:
        async with self._lock:
            try:
                return await asyncio.to_thread(self._get_document, run_id)
            except (sqlite3.Error, ValueError, TypeError) as exc:
                raise OCRStorageError("Could not load document") from exc

    def _get_document(self, run_id: int) -> DocumentDetail | None:
        connection = self._require_connection()
        row = connection.execute(
            """SELECT r.*, e.result_json FROM ocr_runs r
               LEFT JOIN document_extractions e ON e.run_id = r.id WHERE r.id = ?""",
            (run_id,),
        ).fetchone()
        if row is None:
            return None
        regions = connection.execute(
            "SELECT * FROM ocr_regions WHERE run_id = ? ORDER BY ordinal", (run_id,)
        ).fetchall()
        result = (
            ExtractionResult.model_validate_json(row["result_json"])
            if row["result_json"] is not None else None
        )
        return DocumentDetail(
            id=row["id"], image_basename=row["image_basename"],
            created_at=row["created_at"], ocr_model=row["model_version"],
            status="extracted" if result is not None else "ocr_only",
            document_type=result.document_type if result else None,
            number=result.number if result else None,
            municipality=result.municipality if result else None,
            extraction=result,
            ocr=OCRResult(
                content=row["raw_text"], model_version=row["model_version"],
                duration_ms=row["duration_ms"], warnings=json.loads(row["warnings_json"]),
                regions=[_restore_region(region) for region in regions],
            ),
        )

    def _open_database(self) -> sqlite3.Connection:
        if str(self._database_path) != ":memory:":
            self._database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(
            str(self._database_path), check_same_thread=False
        )
        try:
            if str(self._database_path) != ":memory:":
                os.chmod(self._database_path, 0o600)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            if str(self._database_path) != ":memory:":
                connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript(SCHEMA)
        except Exception:
            connection.close()
            raise
        return connection

    def _save(
        self, image_basename: str, image_sha256: str, ocr: OCRResult
    ) -> int:
        connection = self._require_connection()
        with connection:
            cursor = connection.execute(
                """INSERT INTO ocr_runs
                (image_basename, image_sha256, raw_text, model_version,
                 duration_ms, warnings_json)
                VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    image_basename,
                    image_sha256,
                    ocr.content,
                    ocr.model_version,
                    ocr.duration_ms,
                    json.dumps(ocr.warnings, ensure_ascii=False),
                ),
            )
            run_id = cursor.lastrowid
            if run_id is None:
                raise sqlite3.DatabaseError("OCR run ID was not generated")
            connection.executemany(
                """INSERT INTO ocr_regions
                (run_id, ordinal, region_id, text, page, kind, bounding_box_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    _region_row(run_id, ordinal, region)
                    for ordinal, region in enumerate(ocr.regions)
                ),
            )
        return run_id

    def _load_latest(self, image_sha256: str) -> StoredOCRRun | None:
        connection = self._require_connection()
        run = connection.execute(
            """SELECT id, image_basename, image_sha256, raw_text,
                      model_version, duration_ms, warnings_json, created_at
               FROM ocr_runs WHERE image_sha256 = ?
               ORDER BY id DESC LIMIT 1""",
            (image_sha256,),
        ).fetchone()
        if run is None:
            return None
        regions = connection.execute(
            """SELECT region_id, text, page, kind, bounding_box_json
               FROM ocr_regions WHERE run_id = ? ORDER BY ordinal""",
            (run["id"],),
        ).fetchall()
        ocr = OCRResult(
            content=run["raw_text"],
            regions=[_restore_region(region) for region in regions],
            model_version=run["model_version"],
            duration_ms=run["duration_ms"],
            warnings=json.loads(run["warnings_json"]),
        )
        return StoredOCRRun(
            id=run["id"],
            image_basename=run["image_basename"],
            image_sha256=run["image_sha256"],
            created_at=run["created_at"],
            ocr=ocr,
        )

    def _require_connection(self) -> sqlite3.Connection:
        if self._connection is None:
            raise OCRStorageError("OCR storage is not initialized")
        return self._connection


def _region_row(
    run_id: int, ordinal: int, region: OCRRegion
) -> tuple[int, int, str, str | None, int | None, str | None, str | None]:
    bounding_box = getattr(region, "bounding_box", None)
    return (
        run_id,
        ordinal,
        region.id,
        region.text,
        getattr(region, "page", None),
        getattr(region, "kind", None),
        json.dumps(bounding_box) if bounding_box is not None else None,
    )


def _restore_region(row: sqlite3.Row) -> OCRRegion:
    return OCRRegion(
        id=row["region_id"],
        text=row["text"],
        page=row["page"],
        kind=row["kind"],
        bounding_box=(
            json.loads(row["bounding_box_json"])
            if row["bounding_box_json"] is not None
            else None
        ),
    )


def _validate_source_identity(image_basename: str, image_sha256: str) -> None:
    if not image_basename or "/" in image_basename or "\\" in image_basename:
        raise ValueError("image_basename must not contain a path")
    _validate_sha256(image_sha256)


def _validate_sha256(image_sha256: str) -> None:
    if re.fullmatch(r"[0-9a-f]{64}", image_sha256) is None:
        raise ValueError("image_sha256 must be a lowercase SHA-256 digest")
