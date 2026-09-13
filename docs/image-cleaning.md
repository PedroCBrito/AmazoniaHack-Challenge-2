# Image cleaning before OCR

## Project review and implementation sequence

The existing `/extract` route delegates to `ExtractionService`, then
`prepare_image`, `ChandraClient`, the private OCR adapter, and the field mapper.
Preparation previously checked JPEG/PNG metadata and limits and applied EXIF
orientation. It did not correct shadows, noise, or paper color. Both Chandra and
Textract receive the same application payload, so preparation is the shared place
to improve their input without coupling image processing to a provider.

The implementation follows these steps:

1. Retain upload validation, EXIF orientation, the multipart OCR contract, and the
   review-oriented JSON response.
2. Isolate deterministic processing in `app/services/image_cleaner.py`, with no
   HTTP, configuration, filesystem, logging, or OCR dependencies in the function.
3. Integrate it in `app/services/image_processor.py` after input validation and
   orientation, before encoding and `ChandraClient.recognize`.
4. Add pinned NumPy and headless OpenCV dependencies to `requirements.txt`, which
   is consumed by development installation and the Docker dependency stage.
5. Add a default-on setting, `APP_IMAGE_CLEANING_ENABLED`, and pass it through
   Compose for repeatable comparisons and rollback.
6. Validate image quality on deterministic samples and verify upload handling,
   actual outbound multipart bytes, failures, and cancellation behavior.
7. Document the new flow and leave actual OCR accuracy evaluation as a separate,
   explicit measurement with annotated documents.

Review also confirmed that the mapper is still `PendingFieldMapper`: `/extract`
returns null business fields and `field_mapping_not_configured`. Cleaning does
not implement field extraction or change this contract. Runtime installation uses
`requirements*.txt`; the existing `pyproject.toml`/`uv.lock` are scaffold metadata
with no application dependency list and are not the installation path used here.
The existing Docker image and local validation environment use Python 3.12, while
that scaffold declares 3.13. Packaging alignment remains separate work.

## Algorithm and rationale

`clean_image(image: PIL.Image.Image) -> PIL.Image.Image` returns a new 8-bit
grayscale image, preserving width and height and leaving input pixels unchanged.
It assumes dark writing on light paper. Its caller owns validation and EXIF.

| Step | Operation | Reason |
|---|---|---|
| Transparency | Composite RGBA, alpha grayscale, and transparent palette images on white | Avoid turning transparent paper black |
| Color normalization | Explicit RGB-to-grayscale conversion | Reduce paper/ink color variation without an RGB/BGR channel swap |
| Bit depth | Scale 16-bit grayscale PNG values to 8-bit | Preserve ink that would be clipped by direct RGB conversion |
| Noise reduction | Bilateral filter: diameter 5, color sigma 25, spatial sigma 3 | Reduce moderate noise while retaining strong edges |
| Background estimation | Morphological closing followed by Gaussian smoothing | Estimate illumination behind writing |
| Illumination correction | Divide denoised intensity by the background, scaled to 255 | Brighten shaded paper relative to the local background |
| Serialization | Lossless PNG with MIME `image/png` and filename `document.png` | Avoid adding JPEG compression artifacts |

The background kernel is rectangular. Its side is
`min(101, max(15, min(height, width) // 40)) | 1`, producing an odd size between
15 and 101. This bounds filter cost and scales the estimation window with page
resolution. Denominators are clamped to at least 1. Images with a side shorter
than 3 pixels receive only compositing and grayscale conversion; their neighbors
provide too little context for reliable background estimation.

No binary threshold, sharpening, cropping, resizing, deskew, or perspective
correction is applied. Grayscale retains intensity gradations in faint writing.
Region boxes still refer to the image after EXIF orientation, as in the existing
OCR contract. These parameters are an initial reproducible policy; change them
only with quality comparisons on the intended document set.

The filter behavior is described in the official
[OpenCV filtering reference](https://docs.opencv.org/4.13.0/d4/d86/group__imgproc__filter.html).
The selected [headless distribution](https://pypi.org/project/opencv-python-headless/4.13.0.92/)
supports server use without GUI dependencies.

## Runtime and error behavior

- `APP_IMAGE_CLEANING_ENABLED=true` is the default. With `false`, validation and
  EXIF normalization still run and the original JPEG/PNG format is retained.
- Validate declared MIME, actual format, nonempty bytes, byte size, readability,
  and pixel count before cleaning. Upload files close even on validation failure.
- `APP_MAX_FILE_SIZE_BYTES` applies again after encoding. PNG may be larger than
  the uploaded JPEG; return `413 prepared_image_too_large` instead of silently
  reducing image quality or forwarding a known oversized payload.
- Configure the adapter and selected provider to accept the prepared byte/pixel
  limits. Provider restrictions can be stricter than the API defaults.
- OpenCV processing errors return `422 image_cleaning_failed`; no original-image
  fallback or OCR call hides this failure. No image contents enter error messages.
- Validation, decoding, cleaning, and encoding run in a worker thread, keeping the
  async API available for liveness and other requests. The existing extraction
  semaphore bounds the complete request, including cleaning.
- Native processing cannot be interrupted safely. If the deadline expires during
  preparation, the API waits for that worker to finish, holds its capacity slot,
  and returns `504 processing_timeout` without calling OCR. The configured deadline
  is therefore not a hard wall-clock limit on native execution. Repeated
  cancellation also waits for native completion before releasing capacity.
- Processing is in memory and does not persist original or cleaned documents.
  Color and filter buffers scale with pixel count; the 40-million-pixel default
  still needs deployment memory sizing. Increase concurrency only after measuring
  peak memory and latency on the target machine.
- The private `/ocr` endpoint validates and forwards its own input. It does not
  repeat application cleaning, including when called directly.

## Reproducible validation

From an activated virtual environment at the repository root:

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q --cov=app --cov=ocr_adapter --cov-report=term-missing
python -m scripts.validate_image_cleaning --output-dir outputs/cleaning-validation
```

The script uses fixed-seed 800 x 600 synthetic pages with black, blue, and red
writing, a thin line, a colored paper tint, a smooth illumination gradient, and
Gaussian noise. It saves reference/before/after PNGs for shadows, noise, colored
paper, and their combination, plus `metrics.json`. Files go under the ignored
`outputs/` directory and contain no real document data. The command exercises the
real cleaner without an OCR server, GPU, AWS credentials, or model downloads.

Automated acceptance criteria are:

- In shadow, noise, and combined cases, background standard deviation decreases
  by at least 50%, and fewer than 1% of known background pixels fall below 180.
- More than 95% of known ink pixels remain below 180 after cleaning; on an already
  clean document, more than 98% remain and a one-pixel line stays visible.
- Colored paper approaches white while colored writing remains distinguishable.
- Input remains unchanged; repeated runs are deterministic; dimensions, uint8
  output, supported color modes, transparency, and uniform/tiny pages are checked.
- Processor tests check JPEG/PNG output metadata, EXIF rotation, the disabled path,
  malformed images, MIME mismatches, limits, and safe OpenCV errors.
- API integration tests inspect the actual multipart request made by `ChandraClient`
  with an HTTP mock. They check both enabled and disabled cleaning, failure before
  OCR, event-loop responsiveness, timeout behavior, and capacity recovery.
  A separate asyncio regression test checks repeated cancellation while native
  processing is still running.

Example local measurements (Python 3.12.3, OpenCV 4.13.0, NumPy 2.2.6):

The complete suite passed locally on 2026-09-13: **77 tests**, with 100% statement
coverage in `image_cleaner.py`, 95% in `image_processor.py`, and 90% overall across
`app` and `ocr_adapter`. `python -m pip check` reported no broken requirements.
Compose and wrapper OpenAPI YAML parsed successfully. Docker containers and live
OCR providers were not exercised in this validation.

| Synthetic case | Background std before | Background std after | Ink retained below 180 |
|---|---:|---:|---:|
| Shadows | 41.98 | 0.19 | 97.03% |
| Noise | 4.81 | 1.37 | 98.40% |
| Colored paper | 0.00 | 0.00 | 98.63% |
| Combined | 39.92 | 2.58 | 97.34% |

Colored-paper mean intensity increased from 240 to 255. The combined case's false
ink background fraction fell from 46.70% to zero. These are image-level metrics
using masks from the ideal page, not OCR character accuracy or proof that every
stroke was preserved. Runtime measurements in the generated JSON depend on the
machine and cover cleaning only, excluding HTTP, encoding, and inference.

## Validate recognition on real documents

1. Select representative photographs and manually verified transcriptions,
   covering shadows, noise, different inks, handwriting, and already clean pages.
2. Keep the provider, model revision, and inference parameters fixed. Save one
   EXIF-normalized baseline and one cleaned PNG for each source. Keep those files
   local according to the project's data-handling policy.
3. Send each prepared image to the same private `/ocr` service. Direct `/ocr`
   calls accept the chosen bytes without applying this cleaner a second time.
4. Compare returned `content` with the transcription using character error rate
   (CER) and word error rate (WER). Normalize layout markup and whitespace with
   the same rules in both runs. Review regressions in accents, digits, signatures,
   faint strokes, and colored marks, and verify region alignment.
5. Record before/after error rates by document category, latency, peak memory,
   versions, settings, and sample identifiers. Define acceptable regressions and
   gains before tuning. Use the disabled setting if a document category regresses.

Actual OCR comparisons and Docker runtime validation require the corresponding
services and are separate from these offline checks. Field-level accuracy cannot
be inferred from the current `/extract` response while field mapping is pending.

## Limits

Cleaning cannot restore missing, clipped, severely blurred, or unreadable text and
does not guarantee perfect extraction. Grayscale discards color semantics, and
very faint ink, isolated marks, strong impulse noise, large dark areas, sharp
shadow boundaries, or light text on dark paper may need a different policy. The
current tests use synthetic printing and a thin line, not a labeled handwriting
corpus. Validate actual document categories before claiming OCR improvement;
human review remains required.
