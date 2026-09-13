"""Deterministic document cleaning, independent of uploads and OCR providers."""

import cv2
import numpy as np
from PIL import Image


def _grayscale_on_white(image: Image.Image) -> np.ndarray:
    if image.mode.startswith("I;16") or image.mode == "I":
        # Pillow's RGB conversion clips 16-bit PNG values above 255. Scale their
        # full range instead, so nonzero dark writing does not become white.
        pixels = np.asarray(image)
        return np.rint(np.clip(pixels, 0, 65535) / 257).astype(np.uint8)
    # Composite all transparency modes (including palette PNGs) onto white paper.
    if (
        image.mode in {"RGBA", "LA", "PA"}
        or "transparency" in image.info
        or (image.palette is not None and image.palette.mode == "RGBA")
    ):
        rgba = image.convert("RGBA")
        paper = Image.new("RGBA", image.size, "white")
        image = Image.alpha_composite(paper, rgba)
    return cv2.cvtColor(np.asarray(image.convert("RGB")), cv2.COLOR_RGB2GRAY)


def clean_image(image: Image.Image) -> Image.Image:
    """Return an 8-bit grayscale image with the same size, without mutating input.

    Assumes dark writing on light paper. Call after EXIF orientation and input
    validation. Avoid thresholding and geometric transforms to retain faint
    handwriting and the coordinate system used by OCR regions.
    """
    # Release color/compositing buffers before allocating filter intermediates.
    gray = _grayscale_on_white(image)

    # Tiny images have too little context to estimate a document background.
    if min(gray.shape) < 3:
        return Image.fromarray(gray)

    denoised = cv2.bilateralFilter(gray, d=5, sigmaColor=25, sigmaSpace=3)
    # A bounded, resolution-dependent window suppresses writing in the estimated
    # paper background. Rectangular morphology keeps large-page cost manageable.
    window = min(101, max(15, min(gray.shape) // 40)) | 1
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (window, window))
    background = cv2.morphologyEx(denoised, cv2.MORPH_CLOSE, kernel)
    background = cv2.GaussianBlur(background, (window, window), 0)
    # Division compensates for uneven illumination. Guard black pages against
    # zero division, without stretching flat input into artificial text.
    cleaned = cv2.divide(denoised, np.maximum(background, 1), scale=255)
    return Image.fromarray(cleaned)
