import asyncio
import hashlib
import io
import warnings
from dataclasses import dataclass

import cv2
from fastapi import UploadFile
from PIL import Image, ImageOps, UnidentifiedImageError

from app.core.config import Settings
from app.core.errors import ApplicationError
from app.services.image_cleaner import clean_image


ALLOWED_CONTENT_TYPES = {"image/jpeg": "JPEG", "image/png": "PNG"}
FORMAT_CONTENT_TYPES = {value: key for key, value in ALLOWED_CONTENT_TYPES.items()}


@dataclass(frozen=True, slots=True)
class PreparedImage:
    content: bytes
    content_type: str
    filename: str
    width: int
    height: int
    source_basename: str
    source_sha256: str


async def prepare_image(upload: UploadFile, settings: Settings) -> PreparedImage:
    """Read a bounded upload and prepare it off the event loop for OCR."""
    content_type = upload.content_type
    source_basename = _safe_source_basename(upload.filename)
    try:
        if content_type not in ALLOWED_CONTENT_TYPES:
            raise ApplicationError(
                415, "unsupported_media_type", "Only JPEG and PNG images are accepted."
            )
        content = await upload.read(settings.max_file_size_bytes + 1)
    finally:
        await upload.close()
    if len(content) > settings.max_file_size_bytes:
        raise ApplicationError(413, "file_too_large", "The image exceeds the file limit.")
    if not content:
        raise ApplicationError(422, "invalid_image", "The uploaded image is empty.")

    worker = asyncio.create_task(
        asyncio.to_thread(
            _prepare_image_bytes, content, content_type, source_basename, settings
        )
    )
    try:
        return await asyncio.shield(worker)
    except asyncio.CancelledError:
        # Native processing cannot be interrupted. Keep the extraction slot until
        # it finishes, so timed-out requests cannot accumulate background work.
        completion = asyncio.gather(worker, return_exceptions=True)
        while not completion.done():
            try:
                await asyncio.shield(completion)
            except asyncio.CancelledError:
                # A second cancellation (for example during server shutdown)
                # must not cancel the worker task and release its slot early.
                continue
        raise


def _prepare_image_bytes(
    content: bytes,
    content_type: str,
    source_basename: str,
    settings: Settings,
) -> PreparedImage:
    """Validate before allocating cleaning buffers, then orient and encode."""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(content)) as opened:
                detected_format = opened.format
                width, height = opened.size
                if width * height > settings.max_image_pixels:
                    raise ApplicationError(
                        413,
                        "image_too_large",
                        "The decoded image exceeds the pixel limit.",
                    )
                opened.verify()
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ApplicationError(
            413, "image_too_large", "The decoded image exceeds the safety limit."
        ) from exc
    except (
        UnidentifiedImageError,
        OSError,
        SyntaxError,
    ) as exc:
        raise ApplicationError(
            422, "invalid_image", "The file is not a valid, readable image."
        ) from exc

    if detected_format not in FORMAT_CONTENT_TYPES:
        raise ApplicationError(
            415, "unsupported_media_type", "Only JPEG and PNG images are accepted."
        )
    if FORMAT_CONTENT_TYPES[detected_format] != content_type:
        raise ApplicationError(
            415,
            "media_type_mismatch",
            "The declared media type does not match the image bytes.",
        )
    try:
        with Image.open(io.BytesIO(content)) as opened:
            normalized = ImageOps.exif_transpose(opened)
            normalized.load()
            output_format = detected_format
            if settings.image_cleaning_enabled:
                try:
                    normalized = clean_image(normalized)
                except (cv2.error, ValueError) as exc:
                    raise ApplicationError(
                        422, "image_cleaning_failed", "The image could not be cleaned."
                    ) from exc
                # Lossless output avoids new JPEG artifacts after cleaning.
                output_format = "PNG"
            output = io.BytesIO()
            if output_format == "JPEG" and normalized.mode not in ("RGB", "L"):
                normalized = normalized.convert("RGB")
            save_options = {"quality": 95} if output_format == "JPEG" else {}
            normalized.save(output, format=output_format, **save_options)
    except (OSError, SyntaxError, ValueError) as exc:
        raise ApplicationError(
            422, "invalid_image", "The image could not be normalized."
        ) from exc

    prepared_content = output.getvalue()
    if len(prepared_content) > settings.max_file_size_bytes:
        raise ApplicationError(
            413,
            "prepared_image_too_large",
            "The prepared image exceeds the file limit.",
        )
    safe_filename = f"document.{output_format.lower()}"
    return PreparedImage(
        content=prepared_content,
        content_type=FORMAT_CONTENT_TYPES[output_format],
        filename=safe_filename,
        width=normalized.width,
        height=normalized.height,
        source_basename=source_basename,
        source_sha256=hashlib.sha256(content).hexdigest(),
    )


def _safe_source_basename(filename: str | None) -> str:
    basename = (filename or "document").replace("\\", "/").rsplit("/", 1)[-1]
    printable = "".join(character for character in basename if character.isprintable())
    return printable.strip() or "document"
