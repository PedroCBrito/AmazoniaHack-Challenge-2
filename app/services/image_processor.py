import io
import warnings
from dataclasses import dataclass

from fastapi import UploadFile
from PIL import Image, ImageOps, UnidentifiedImageError

from app.core.config import Settings
from app.core.errors import ApplicationError


ALLOWED_CONTENT_TYPES = {"image/jpeg": "JPEG", "image/png": "PNG"}
FORMAT_CONTENT_TYPES = {value: key for key, value in ALLOWED_CONTENT_TYPES.items()}


@dataclass(frozen=True, slots=True)
class PreparedImage:
    content: bytes
    content_type: str
    filename: str
    width: int
    height: int


async def prepare_image(upload: UploadFile, settings: Settings) -> PreparedImage:
    """Validate image bytes, apply EXIF orientation, and normalize the payload."""

    if upload.content_type not in ALLOWED_CONTENT_TYPES:
        raise ApplicationError(
            415, "unsupported_media_type", "Only JPEG and PNG images are accepted."
        )

    content = await upload.read(settings.max_file_size_bytes + 1)
    await upload.close()
    if len(content) > settings.max_file_size_bytes:
        raise ApplicationError(413, "file_too_large", "The image exceeds the file limit.")
    if not content:
        raise ApplicationError(422, "invalid_image", "The uploaded image is empty.")

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
    if FORMAT_CONTENT_TYPES[detected_format] != upload.content_type:
        raise ApplicationError(
            415,
            "media_type_mismatch",
            "The declared media type does not match the image bytes.",
        )
    try:
        with Image.open(io.BytesIO(content)) as opened:
            normalized = ImageOps.exif_transpose(opened)
            normalized.load()
            output = io.BytesIO()
            if detected_format == "JPEG" and normalized.mode not in ("RGB", "L"):
                normalized = normalized.convert("RGB")
            save_options = {"quality": 95} if detected_format == "JPEG" else {}
            normalized.save(output, format=detected_format, **save_options)
    except (OSError, SyntaxError, ValueError) as exc:
        raise ApplicationError(
            422, "invalid_image", "The image could not be normalized."
        ) from exc

    safe_filename = f"document.{detected_format.lower()}"
    return PreparedImage(
        content=output.getvalue(),
        content_type=FORMAT_CONTENT_TYPES[detected_format],
        filename=safe_filename,
        width=normalized.width,
        height=normalized.height,
    )
