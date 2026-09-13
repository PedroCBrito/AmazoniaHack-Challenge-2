"""Export one validated /extract response per image, using the same basename."""

import argparse
from pathlib import Path
import sys

import httpx
from pydantic import ValidationError

from app.schemas.extraction import ExtractionResult


MEDIA_TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}


def export_images(images: list[Path], output_dir: Path, client: httpx.Client) -> list[Path]:
    """Preflight collisions; never overwrite existing files or save API errors as data."""
    targets = [output_dir / f"{image.stem}.json" for image in images]
    if len({str(target.resolve()).casefold() for target in targets}) != len(targets):
        raise ValueError("Input images have conflicting output basenames.")
    for image, target in zip(images, targets, strict=True):
        if image.suffix.lower() not in MEDIA_TYPES or not image.is_file():
            raise ValueError("Every input must be an existing JPEG or PNG file.")
        if target.exists():
            raise FileExistsError("An output JSON already exists; select another output directory.")
    output_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for image, target in zip(images, targets, strict=True):
        with image.open("rb") as upload:
            response = client.post("/extract", files={"image": (image.name, upload, MEDIA_TYPES[image.suffix.lower()])})
        response.raise_for_status()
        result = ExtractionResult.model_validate(response.json())
        serialized = result.model_dump_json(by_alias=True, indent=2) + "\n"
        # Exclusive creation also handles a file appearing after the preflight.
        destination = target.open("x", encoding="utf-8", newline="\n")
        try:
            with destination:
                destination.write(serialized)
        except BaseException:
            target.unlink(missing_ok=True)
            raise
        written.append(target)
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("images", nargs="+", type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path("outputs"))
    parser.add_argument("--api-url", default="http://127.0.0.1:8000")
    parser.add_argument("--timeout", type=float, default=180)
    args = parser.parse_args(argv)
    if not 0 < args.timeout < float("inf"):
        parser.error("--timeout must be a finite positive number")
    try:
        with httpx.Client(base_url=args.api_url, timeout=args.timeout) as client:
            written = export_images(args.images, args.output_dir, client)
    except httpx.HTTPStatusError as exc:
        print(f"Export stopped: API returned HTTP {exc.response.status_code}. No JSON was saved for that image.", file=sys.stderr)
        return 1
    except httpx.HTTPError:
        print("Export stopped: the API could not be reached or timed out.", file=sys.stderr)
        return 1
    except ValidationError:
        print("Export stopped: the API response does not match the extraction schema.", file=sys.stderr)
        return 1
    except (OSError, ValueError):
        print("Export stopped: check input files, unique basenames, output permissions, existing outputs, and response JSON.", file=sys.stderr)
        return 1
    for target in written:
        print(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
