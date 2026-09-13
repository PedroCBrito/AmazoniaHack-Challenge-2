"""Explicitly save OCR and mapping for local diagnosis; never overwrite a run."""

import argparse
import asyncio
import json
from pathlib import Path
import time

from fastapi import UploadFile
import httpx
from starlette.datastructures import Headers

from app.core.config import Settings
from app.schemas.ocr import OCRResult
from app.services.field_mapper import RuleBasedFieldMapper
from app.services.image_processor import prepare_image
from app.services.ocr_client import ChandraClient


async def diagnose(source: Path, output: Path, from_ocr: bool, ocr_url: str) -> None:
    if output.exists():
        raise ValueError("Use a new output directory for each diagnostic run.")
    started = time.perf_counter()
    if from_ocr:
        ocr = OCRResult.model_validate_json(source.read_text(encoding="utf-8"))
    else:
        settings = Settings(_env_file=".env.local")
        media_type = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}[source.suffix.lower()]
        with source.open("rb") as stream:
            upload = UploadFile(stream, filename=source.name, headers=Headers({"content-type": media_type}))
            prepared = await prepare_image(upload, settings)
        async with httpx.AsyncClient(base_url=ocr_url, timeout=settings.chandra_timeout_seconds) as client:
            ocr = await ChandraClient(client).recognize(prepared)
    result = await RuleBasedFieldMapper().map(ocr)
    result.meta.duration_ms = int((time.perf_counter() - started) * 1000)
    output.mkdir(parents=True, exist_ok=False)
    (output / "ocr.json").write_text(ocr.model_dump_json(indent=2), encoding="utf-8")
    (output / "mapped.json").write_text(result.model_dump_json(indent=2, by_alias=True), encoding="utf-8")
    print(json.dumps({"output": str(output), "regions": len(ocr.regions),
                      "extracted": [name for name, review in result.review.items() if review.status == "extracted"]}))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--from-ocr", action="store_true", help="Reuse saved OCR without running inference")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--ocr-url", default="http://127.0.0.1:9000")
    args = parser.parse_args()
    asyncio.run(diagnose(args.source, args.output_dir, args.from_ocr, args.ocr_url))


if __name__ == "__main__":
    main()
