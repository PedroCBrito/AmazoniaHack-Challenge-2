"""Generate reproducible synthetic evidence; no OCR service or real data needed."""

import argparse
import json
import time
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from app.services.image_cleaner import clean_image


def document_sample(
    *, shadows: bool = True, noise: float = 8, tint: bool = True
) -> tuple[Image.Image, Image.Image]:
    """Return an ideal page and a degraded copy using a fixed random seed."""
    ideal = Image.new("RGB", (800, 600), "white")
    draw = ImageDraw.Draw(ideal)
    font = ImageFont.load_default(size=28)
    for index, color in enumerate(((25, 25, 25), (20, 45, 160), (170, 30, 30))):
        y = 80 + index * 150
        draw.text((60, y), "AUTO DE INFRACAO 000123/2026", fill=color, font=font)
        draw.text((60, y + 42), "Area: 12,50 ha - Valor: 1500,00", fill=color, font=font)
    draw.line((60, 560, 730, 560), fill=(90, 90, 90), width=1)
    pixels = np.asarray(ideal).astype(np.float32)
    if tint:
        pixels *= np.array([1.0, 0.94, 0.82], dtype=np.float32)
    if shadows:
        illumination = np.linspace(0.45, 1.0, ideal.width, dtype=np.float32)
        pixels *= illumination[None, :, None]
    pixels += np.random.default_rng(42).normal(0, noise, pixels.shape)
    degraded = Image.fromarray(np.clip(pixels, 0, 255).astype(np.uint8))
    return ideal, degraded


def quality_metrics(reference: Image.Image, image: Image.Image) -> dict[str, float]:
    """Measure known paper and ink regions, not OCR recognition accuracy."""
    reference_gray = np.asarray(reference.convert("L"))
    pixels = np.asarray(image.convert("L"))
    ink = reference_gray < 180
    # Exclude anti-aliasing and a margin around writing from background measures.
    near_ink = cv2.dilate(
        (reference_gray < 255).astype(np.uint8), np.ones((15, 15), np.uint8)
    )
    background = pixels[near_ink == 0]
    return {
        "background_std": float(background.std()),
        "background_mean": float(background.mean()),
        "ink_recall_below_180": float((pixels[ink] < 180).mean()),
        "background_false_ink_below_180": float((background < 180).mean()),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/cleaning-validation"))
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    report = {}
    for name, options in {
        "shadows": {"noise": 0, "tint": False},
        "noise": {"shadows": False, "noise": 12, "tint": False},
        "colored_paper": {"shadows": False, "noise": 0},
        "combined": {},
    }.items():
        ideal, degraded = document_sample(**options)
        started = time.perf_counter()
        cleaned = clean_image(degraded)
        duration_ms = (time.perf_counter() - started) * 1000
        ideal.save(args.output_dir / f"{name}-reference.png")
        degraded.save(args.output_dir / f"{name}-before.png")
        cleaned.save(args.output_dir / f"{name}-after.png")
        report[name] = {
            "before": quality_metrics(ideal, degraded),
            "after": quality_metrics(ideal, cleaned),
            "duration_ms": duration_ms,
        }
    payload = json.dumps(report, indent=2)
    (args.output_dir / "metrics.json").write_text(payload + "\n", encoding="utf-8")
    print(payload)


if __name__ == "__main__":
    main()
