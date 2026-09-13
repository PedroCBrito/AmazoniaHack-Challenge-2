import numpy as np
import pytest
from PIL import Image, ImageDraw

from app.services.image_cleaner import clean_image
from scripts.validate_image_cleaning import document_sample, quality_metrics


@pytest.mark.parametrize(
    "options",
    [
        {"noise": 0, "tint": False},
        {"shadows": False, "noise": 12, "tint": False},
        {},
    ],
    ids=["shadows", "noise", "combined"],
)
def test_cleaning_reduces_background_variation_and_preserves_ink(options) -> None:
    reference, degraded = document_sample(**options)
    cleaned = clean_image(degraded)
    before = quality_metrics(reference, degraded)
    after = quality_metrics(reference, cleaned)

    assert after["background_std"] < before["background_std"] * 0.5
    assert after["background_false_ink_below_180"] < 0.01
    assert after["ink_recall_below_180"] > 0.95
    assert cleaned.size == degraded.size
    assert cleaned.mode == "L"


def test_colored_paper_is_whitened_without_losing_colored_writing() -> None:
    reference, degraded = document_sample(shadows=False, noise=0)
    after = quality_metrics(reference, clean_image(degraded))
    assert after["background_mean"] > 250
    assert after["ink_recall_below_180"] > 0.95


def test_clean_document_and_single_pixel_strokes_remain_legible() -> None:
    reference, _ = document_sample(shadows=False, noise=0, tint=False)
    cleaned = np.asarray(clean_image(reference))
    metrics = quality_metrics(reference, Image.fromarray(cleaned))
    assert metrics["ink_recall_below_180"] > 0.98
    assert (cleaned[560, 60:730] < 180).all()
    assert metrics["background_mean"] > 250


def test_cleaning_is_deterministic_and_does_not_mutate_input() -> None:
    _, image = document_sample()
    original = image.tobytes()
    first = clean_image(image)
    second = clean_image(image)
    assert first.tobytes() == second.tobytes()
    assert image.tobytes() == original


@pytest.mark.parametrize("mode", ["RGB", "L", "RGBA", "LA", "P", "1"])
def test_supported_pillow_modes(mode: str) -> None:
    image = Image.new("RGB", (40, 30), "white")
    ImageDraw.Draw(image).line((10, 5, 10, 25), fill="black", width=2)
    cleaned = np.asarray(clean_image(image.convert(mode)))
    assert cleaned.shape == (30, 40)
    assert cleaned.dtype == np.uint8
    assert cleaned[10, 10] < 50
    assert cleaned[0, 0] > 250


@pytest.mark.parametrize("mode", ["RGBA", "LA", "P"])
def test_transparent_background_becomes_white(mode: str) -> None:
    image = Image.new("RGBA", (40, 30), (0, 0, 0, 0))
    ImageDraw.Draw(image).line((10, 5, 10, 25), fill=(0, 0, 0, 255), width=2)
    image = image.convert(mode)
    cleaned = np.asarray(clean_image(image))
    assert cleaned[0, 0] >= 254  # OpenCV's uint8 filters can round by one level.
    assert cleaned[10, 10] == 0


@pytest.mark.parametrize("size", [(1, 1), (1, 20), (20, 1), (2, 2), (3, 3), (50, 50)])
@pytest.mark.parametrize("color", ["black", "white", "gray"])
def test_tiny_and_uniform_images_do_not_gain_artificial_text(size, color) -> None:
    cleaned = np.asarray(clean_image(Image.new("RGB", size, color)))
    assert cleaned.shape == (size[1], size[0])
    assert cleaned.max() == cleaned.min()
    if color == "black":
        assert cleaned.max() == 0
