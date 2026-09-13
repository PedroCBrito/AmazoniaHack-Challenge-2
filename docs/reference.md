# Reference

## Commands

| Command | Purpose |
|---|---|
| `just help` | List recipes |
| `just start` | Build and start API and OCR containers |
| `just stop` | Stop API and OCR containers |
| `just dev-api` | Run API with hot reload |
| `just dev-ocr` | Run OCR adapter with hot reload |
| `just test` | Run tests |
| `just coverage` | Run tests with coverage |

## OCR configuration

| Variable | Values/default | Purpose |
|---|---|---|
| `OCR_PROVIDER` | `chandra` or `textract` | Select backend |
| `OCR_BACKEND_BASE_URL` | `http://llamactl:9099/v1` | Chandra-compatible endpoint |
| `OCR_BACKEND_MODEL` | `chandra-ocr` | Chandra model name |
| `OCR_BACKEND_API_KEY` | empty | Optional bearer token |
| `AWS_PROFILE` | empty | AWS CLI profile for Textract |
| `AWS_REGION` | `eu-central-1` | AWS region |
| `AWS_CONFIG_DIR` | none | Host AWS config directory for Docker |
| `OCR_CONTAINER_UID/GID` | `1000/1000` | OCR container identity; use `0/0` for rootless mode with mode-600 AWS files |

## Image preparation configuration

| Variable | Default | Purpose |
|---|---|---|
| `APP_IMAGE_CLEANING_ENABLED` | `true` | Clean before OCR; `false` keeps validation and EXIF normalization only |
| `APP_MAX_FILE_SIZE_BYTES` | `15728640` | Limit both the upload and the encoded prepared image |
| `APP_MAX_IMAGE_PIXELS` | `40000000` | Reject excessive dimensions before decoding and cleaning |
| `APP_MAX_CONCURRENT_REQUESTS` | `1` | Bound preparation, OCR, and mapping together |
| `APP_PROCESSING_DEADLINE_SECONDS` | `120` | Processing deadline; native cleaning must finish before its slot is released |

Cleaning returns grayscale PNG internally, including for JPEG uploads. No endpoint
or response-field change is required. The API returns `422 image_cleaning_failed`
for an OpenCV processing failure, and `413 prepared_image_too_large` if encoding
exceeds the byte limit; neither case invokes OCR. Existing input-validation errors
remain in place. Configure adapter/provider limits to accept the prepared payload.
The cleaning toggle is passed through Docker Compose; the other API limits use
application defaults unless explicitly supplied to the container.

## Adapter endpoints

| Endpoint | Meaning |
|---|---|
| `GET /live` | Process is running |
| `GET /health` | Selected backend is ready |
| `POST /ocr` | Accept one JPEG/PNG and return OCR output |

`POST /ocr` returns `content`, `regions`, `model_version`, `duration_ms`, and `warnings`. Region bounding boxes use decoded image pixel coordinates.

## Application endpoints

| Endpoint | Meaning |
|---|---|
| `GET /live` | API process is running |
| `GET /health` | API and OCR dependency status |
| `POST /extract` | OCR plus field-mapping response |
| `GET /docs` | Interactive OpenAPI documentation |

The current mapper is pending. `/extract` therefore returns null mapped fields, zero confidence, and `field_mapping_not_configured`.

## AWS permissions

The Textract runtime identity needs `textract:DetectDocumentText` on `*`. Direct image bytes do not need S3 permissions. S3 permissions are only needed if the implementation later sends S3 object references.
