# Project Status and Roadmap

## Current status

The project has a functional FastAPI foundation and a defined HTTP boundary for a
self-hosted Chandra OCR service. The API validates, orients, and cleans JPEG/PNG uploads with OpenCV,
calls the OCR wrapper, validates its response shape, handles dependency failures,
and returns the predefined review-oriented JSON schema.

API and OCR run as separate Docker services. The OCR adapter calls a configurable local or remote OpenAI-compatible Chandra backend and converts its response to the project contract.

`/extract` now reaches real OCR through `GET /health` and `POST /ocr`. Business fields remain `null` until the field mapper is implemented.

## Status definitions

- **OK**: implemented and covered by the current test suite.
- **PENDING FINALIZATION**: foundation exists, but integration or production work
  remains.
- **NOT STARTED**: required by the plan but no functional implementation exists.

## Roadmap

| Area | Status | Remaining work |
|---|---|---|
| FastAPI endpoints and output schema | **OK** | Maintain the contract as extraction evolves. |
| JPEG/PNG validation and EXIF preparation | **OK** | Add broader fixtures for large images and EXIF cases. |
| OpenCV image cleaning | **OK** | Implemented before OCR; synthetic quality, mode, EXIF, HTTP, limits, failure, and timeout checks. See [validation](image-cleaning.md). |
| Cleaning impact on actual OCR accuracy | **PENDING FINALIZATION** | Compare CER/WER on representative annotated photographs with each provider; measure target-hardware resources. |
| Docker API/OCR separation | **OK** | Validate the images with Docker Engine in CI or deployment. |
| OCR HTTP client and error mapping | **OK** | Add direct HTTP contract tests for every dependency response. |
| Chandra wrapper contract | **OK** | Keep the Markdown and OpenAPI documents aligned. |
| Chandra OCR adapter | **OK** | Pin the final backend and model artifact revisions. |
| OCR integration testing | **PENDING FINALIZATION** | Add a repeatable real-model fixture and measure latency. |
| Field extraction mapper | **NOT STARTED** | Map OCR content to the predefined environmental document fields. |
| Semantic validation and evidence checks | **PENDING FINALIZATION** | Validate identifiers, dates, references, coordinates, areas, fines, and source excerpts. |
| Heuristic confidence and field warnings | **PENDING FINALIZATION** | Generate conservative review priorities from real mapped fields. |
| JSON export CLI | **NOT STARTED** | Save one JSON file per image using the same basename. |
| Evaluation and resource reporting | **NOT STARTED** | Measure field errors, missing values, latency, CPU/GPU use, and memory. |
| Production model and hardware guide | **NOT STARTED** | Record tested versions, checkpoint revision, hardware, and runtime configuration. |

## Recommended next steps

1. Pin the llama.cpp image and Chandra GGUF artifacts.
2. Add repeatable end-to-end OCR checks using representative Portuguese documents.
3. Implement the field mapper and strict dependency-output handling.
4. Complete semantic validation, evidence checks, confidence, and warnings.
5. Add the export CLI, evaluation suite, and production deployment measurements.
