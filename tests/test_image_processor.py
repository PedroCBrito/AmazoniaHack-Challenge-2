import asyncio
import hashlib
import io
import threading

import cv2
import numpy as np
import pytest
from fastapi import UploadFile
from PIL import Image, ImageDraw
from starlette.datastructures import Headers

from app.core.config import Settings
from app.core.errors import ApplicationError
from app.services.image_processor import prepare_image


pytestmark = pytest.mark.anyio


def upload_image(image: Image.Image, image_format: str = "PNG", **save_options) -> UploadFile:
    output = io.BytesIO()
    image.save(output, format=image_format, **save_options)
    output.seek(0)
    content_type = "image/jpeg" if image_format == "JPEG" else "image/png"
    return UploadFile(
        output,
        filename="untrusted-name",
        headers=Headers({"content-type": content_type}),
    )


@pytest.mark.parametrize("image_format", ["JPEG", "PNG"])
async def test_cleaned_payload_is_lossless_png_with_consistent_metadata(image_format) -> None:
    upload = upload_image(Image.new("RGB", (60, 40), (200, 180, 150)), image_format)
    prepared = await prepare_image(
        upload, Settings(_env_file=None, image_cleaning_enabled=True)
    )
    assert upload.file.closed
    assert prepared.filename == "document.png"
    assert prepared.content_type == "image/png"
    assert (prepared.width, prepared.height) == (60, 40)
    with Image.open(io.BytesIO(prepared.content)) as decoded:
        assert decoded.format == "PNG"
        assert decoded.mode == "L"
        assert np.asarray(decoded).min() > 250


@pytest.mark.parametrize("image_format", ["JPEG", "PNG"])
async def test_disabled_cleaning_preserves_color_and_format(image_format, monkeypatch) -> None:
    def unexpected_cleaning(_image):
        pytest.fail("Cleaning must not run when disabled")

    monkeypatch.setattr("app.services.image_processor.clean_image", unexpected_cleaning)
    upload = upload_image(Image.new("RGB", (60, 40), (200, 180, 150)), image_format)
    prepared = await prepare_image(upload, Settings(_env_file=None, image_cleaning_enabled=False))
    with Image.open(io.BytesIO(prepared.content)) as decoded:
        assert decoded.format == image_format
        assert decoded.mode == "RGB"
        assert abs(decoded.getpixel((0, 0))[0] - 200) <= 2


async def test_prepared_image_keeps_safe_original_identity() -> None:
    upload = upload_image(Image.new("RGB", (40, 40), "white"))
    upload.filename = "../../issued-notice.png"
    original = upload.file.getvalue()

    prepared = await prepare_image(upload, Settings(_env_file=None))

    assert prepared.source_basename == "issued-notice.png"
    assert prepared.source_sha256 == hashlib.sha256(original).hexdigest()


@pytest.mark.parametrize("enabled", [True, False])
async def test_exif_orientation_applies_once_and_preserves_region_coordinates(enabled) -> None:
    image = Image.new("RGB", (60, 40), "white")
    ImageDraw.Draw(image).rectangle((5, 5, 10, 10), fill="black")
    exif = Image.Exif()
    exif[274] = 6  # Rotate 90 degrees clockwise.
    prepared = await prepare_image(
        upload_image(image, "JPEG", exif=exif),
        Settings(_env_file=None, image_cleaning_enabled=enabled),
    )
    assert (prepared.width, prepared.height) == (40, 60)
    with Image.open(io.BytesIO(prepared.content)) as decoded:
        assert decoded.getexif().get(274) is None
        assert decoded.convert("L").getpixel((32, 7)) < 80
        assert decoded.convert("L").getpixel((7, 7)) > 240


@pytest.mark.parametrize(
    "case, status, code",
    [
        ("empty", 422, "invalid_image"),
        ("corrupt", 422, "invalid_image"),
        ("bytes", 413, "file_too_large"),
        ("pixels", 413, "image_too_large"),
        ("mime", 415, "media_type_mismatch"),
        ("unsupported", 415, "unsupported_media_type"),
    ],
)
async def test_invalid_input_is_rejected_before_cleaning(case, status, code, monkeypatch) -> None:
    def unexpected_cleaning(_image):
        pytest.fail("Invalid input must never reach cleaning")

    monkeypatch.setattr("app.services.image_processor.clean_image", unexpected_cleaning)
    upload = upload_image(Image.new("RGB", (60, 40), "white"))
    settings = Settings(_env_file=None)
    if case in {"empty", "corrupt"}:
        upload.file.close()
        upload.file = io.BytesIO(b"" if case == "empty" else b"invalid bytes")
    elif case == "bytes":
        settings.max_file_size_bytes = 10
    elif case == "pixels":
        settings.max_image_pixels = 100
    elif case == "mime":
        upload.headers = Headers({"content-type": "image/jpeg"})
    else:
        upload.headers = Headers({"content-type": "text/plain"})
    with pytest.raises(ApplicationError) as error:
        await prepare_image(upload, settings)
    assert (error.value.status_code, error.value.code) == (status, code)
    assert upload.file.closed


async def test_opencv_failure_is_mapped_to_application_error(monkeypatch) -> None:
    def failing_cleaner(_image):
        raise cv2.error("internal implementation details")

    monkeypatch.setattr("app.services.image_processor.clean_image", failing_cleaner)
    with pytest.raises(ApplicationError) as error:
        await prepare_image(
            upload_image(Image.new("RGB", (40, 40))),
            Settings(_env_file=None, image_cleaning_enabled=True),
        )
    assert error.value.code == "image_cleaning_failed"
    assert error.value.status_code == 422
    assert "internal" not in error.value.message


async def test_encoded_output_limit_is_checked_even_when_upload_fits(monkeypatch) -> None:
    noise = np.random.default_rng(1).integers(0, 256, (100, 100), dtype=np.uint8)
    monkeypatch.setattr("app.services.image_processor.clean_image", lambda _image: Image.fromarray(noise))
    with pytest.raises(ApplicationError) as error:
        await prepare_image(
            upload_image(Image.new("RGB", (100, 100), "white")),
            Settings(
                _env_file=None,
                image_cleaning_enabled=True,
                max_file_size_bytes=1024,
            ),
        )
    assert error.value.code == "prepared_image_too_large"
    assert error.value.status_code == 413


async def test_16_bit_png_is_scaled_without_clipping_ink_to_white() -> None:
    pixels = np.full((40, 40), 65535, dtype=np.uint16)
    pixels[5:35, 10:12] = 10000
    prepared = await prepare_image(
        upload_image(Image.fromarray(pixels)),
        Settings(_env_file=None, image_cleaning_enabled=True),
    )
    with Image.open(io.BytesIO(prepared.content)) as decoded:
        assert decoded.mode == "L"
        assert decoded.getpixel((10, 20)) < 50
        assert decoded.getpixel((30, 20)) > 250


async def test_palette_png_transparency_survives_upload_decoding() -> None:
    image = Image.new("RGBA", (40, 40), (0, 0, 0, 0))
    ImageDraw.Draw(image).line((10, 5, 10, 35), fill=(0, 0, 0, 255), width=2)
    prepared = await prepare_image(
        upload_image(image.convert("P")),
        Settings(_env_file=None, image_cleaning_enabled=True),
    )
    with Image.open(io.BytesIO(prepared.content)) as decoded:
        assert decoded.getpixel((0, 0)) >= 254
        assert decoded.getpixel((10, 20)) == 0


def test_repeated_cancellation_waits_for_native_processing(monkeypatch) -> None:
    started = threading.Event()
    release = threading.Event()

    def blocked_cleaner(image):
        started.set()
        if not release.wait(timeout=5):
            raise RuntimeError("Test did not release the cleaner")
        return image.convert("L")

    monkeypatch.setattr("app.services.image_processor.clean_image", blocked_cleaner)

    async def exercise_cancellation():
        task = asyncio.create_task(prepare_image(
            upload_image(Image.new("RGB", (40, 40))),
            Settings(_env_file=None, image_cleaning_enabled=True),
        ))
        try:
            assert await asyncio.to_thread(started.wait, 2)
            # A deadline followed by server shutdown can cancel the same task twice.
            task.cancel()
            await asyncio.sleep(0.05)
            task.cancel()
            await asyncio.sleep(0.05)
            assert not task.done(), "Preparation released capacity while its worker was running"
        finally:
            release.set()
            outcome = await asyncio.gather(task, return_exceptions=True)
        assert isinstance(outcome[0], asyncio.CancelledError)

    # Exercise asyncio directly, without the AnyIO test runner's cancellation handling.
    asyncio.run(exercise_cancellation())
