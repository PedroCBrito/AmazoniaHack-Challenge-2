# Project Status and Roadmap

## Current status

The project has a functional FastAPI foundation and a defined HTTP boundary for a
self-hosted Chandra OCR service. The API validates and prepares JPEG/PNG uploads,
calls the OCR wrapper, validates its response shape, handles dependency failures,
and returns the predefined review-oriented JSON schema.

API and OCR run as separate Docker services. The current OCR container is only a
placeholder: it is live but always returns `503 model_not_ready`.

The real OCR service can be connected without changing the API if it implements
`GET /health` and `POST /ocr` according to `chandra-wrapper.md`. After that
integration, `/extract` will reach the real OCR, but business fields will remain
`null` until the field mapper is implemented.

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
| Docker API/OCR separation | **OK** | Validate the images with Docker Engine in CI or deployment. |
| OCR HTTP client and error mapping | **OK** | Add direct HTTP contract tests for every dependency response. |
| Chandra wrapper contract | **OK** | Keep the Markdown and OpenAPI documents aligned. |
| Chandra model service | **PENDING FINALIZATION** | Replace the placeholder and implement real inference on port `9000`. |
| OCR integration testing | **PENDING FINALIZATION** | Test real content, layout regions, timeouts, invalid JSON, and model readiness. |
| Field extraction mapper | **NOT STARTED** | Map OCR content to the predefined environmental document fields. |
| Semantic validation and evidence checks | **PENDING FINALIZATION** | Validate identifiers, dates, references, coordinates, areas, fines, and source excerpts. |
| Heuristic confidence and field warnings | **PENDING FINALIZATION** | Generate conservative review priorities from real mapped fields. |
| JSON export CLI | **NOT STARTED** | Save one JSON file per image using the same basename. |
| Evaluation and resource reporting | **NOT STARTED** | Measure field errors, missing values, latency, CPU/GPU use, and memory. |
| Production model and hardware guide | **NOT STARTED** | Record tested versions, checkpoint revision, hardware, and runtime configuration. |

## Recommended next steps

1. Implement the Chandra wrapper and replace the `ocr-placeholder` Compose target.
2. Add end-to-end OCR contract tests using representative Portuguese documents.
3. Implement the field mapper and strict dependency-output handling.
4. Complete semantic validation, evidence checks, confidence, and warnings.
5. Add the export CLI, evaluation suite, and production deployment measurements.

