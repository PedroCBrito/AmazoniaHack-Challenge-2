# Project Status and Roadmap

## Current status

The project has a functional FastAPI foundation and a defined HTTP boundary for a
self-hosted Chandra OCR service. The API validates, orients, and cleans JPEG/PNG uploads with OpenCV,
calls the OCR wrapper, validates its response shape, handles dependency failures,
and returns the predefined review-oriented JSON schema.

API and OCR run as separate Docker services. The OCR adapter calls a configurable local or remote OpenAI-compatible Chandra backend and converts its response to the project contract.

`/extract` reaches the OCR adapter through `POST /ocr` and maps supported explicit
Portuguese titles/labels with local rules. Unsupported or ambiguous values remain
null with review evidence. See [field mapping](field-mapping.md).

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
| Field extraction mapper | **OK** | Local rules cover supported explicit labels; broaden coverage with annotated real forms. |
| Semantic validation and evidence checks | **PENDING FINALIZATION** | Format/conflict checks and source attribution implemented. Evaluate OCR errors, complex layouts, and cross-field semantics on real documents. |
| Heuristic confidence and field warnings | **PENDING FINALIZATION** | Evidence-based review scores and warnings implemented; calibration on real documents remains. |
| JSON export CLI | **OK** | Validates responses and writes one JSON per basename without overwriting existing files. |
| Evaluation and resource reporting | **NOT STARTED** | Measure field errors, missing values, latency, CPU/GPU use, and memory. |
| Production model and hardware guide | **NOT STARTED** | Record tested versions, checkpoint revision, hardware, and runtime configuration. |

## Recommended next steps

1. Pin the llama.cpp image and Chandra GGUF artifacts.
2. Add repeatable end-to-end OCR checks using representative Portuguese documents.
3. Evaluate the local mapper on representative annotated forms and extend explicit label rules.
4. Measure field errors and calibrate confidence; improve complex layout and partial-field handling.
5. Add production deployment measurements and real-image regression fixtures.
