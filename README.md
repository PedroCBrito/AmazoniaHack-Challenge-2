# EDEX - Environmental Document Extraction

FastAPI service that turns photographed environmental documents into reviewable structured JSON. OCR backends are interchangeable: use local GPU-hosted Chandra or remote Amazon Textract.

Images are validated, EXIF-oriented, and cleaned with OpenCV before OCR. Cleaning
reduces uneven illumination and noise and produces a lossless grayscale PNG.
See [image cleaning: design and validation](docs/image-cleaning.md) for the pipeline,
comparison procedure, and known limits.

## Quick setup

```bash
cp .env.example .env.local
just start
curl http://127.0.0.1:8000/health
curl --fail-with-body -F image=@path/to/document.jpg http://127.0.0.1:8000/extract
```

This starts the API and Chandra OCR adapter. For AWS Textract, configure an AWS profile first and follow the [Textract setup guide](docs/how-to.md#use-textract-with-dev-ocr).

## Start here

- [Tutorial: run the service](docs/tutorial.md)
- [How-to: switch OCR backends and test requests](docs/how-to.md)
- [Reference: commands, configuration, and API](docs/reference.md)
- [Explanation: architecture and processing flow](docs/explanation.md)
- [Image cleaning: implementation and reproducible validation](docs/image-cleaning.md)

## Current status

The API delegates OCR to Chandra or Textract and field mapping to the configured local LLM. `/extract` persists both OCR output and the mapped result in SQLite and returns review metadata plus `_meta.document_id`. `GET /documents` lists the saved history, and `GET /documents/{id}` retrieves OCR text and the extraction without rerunning inference. Existing OCR-only records remain accessible.

The [React frontend](Frontend/README.md) connects upload, document history, and result review to this API. Run `npm ci` and `npm run dev` inside `Frontend`; the development server proxies `/api` to `http://127.0.0.1:8000` by default.

## Improvements

The following work should guide continued development and evaluation:

- [ ] **Validate extraction outputs more thoroughly.** Extend schema and semantic checks for identifiers, dates, coordinates, areas, monetary values, and cross-field consistency. Verify that source evidence supports each extracted value and that missing, unreadable, and ambiguous information receives the correct review status. Evaluate heuristic confidence against human-reviewed results.
- [ ] **Test alternative self-hosted OCR and LLM models.** Benchmark OCR backends and field-mapping models independently on the same evaluation set. Measure character/word error rates, field accuracy, unsupported values, missing fields, latency, throughput, and CPU/GPU memory use. Record model revisions, quantization, prompts, runtime settings, and hardware so comparisons are reproducible.
- [ ] **Review the `document_type` fields.** Validate the supported categories against real documents, including both the main document type and `references[].document_type`. Clarify overlapping categories and handling of unknown or ambiguous types, and keep the backend enum, mapping prompts, frontend labels, and tests aligned.
- [ ] **Persist human review corrections.** Add API and storage support for edited values, confirmations, and review history; frontend edits currently remain local to the session. Preserve the original model output alongside reviewed values and use verified corrections to expand regression coverage.
- [ ] **Measure the impact of image cleaning.** Compare OCR and field extraction with and without cleaning on real photographs, especially faint text, stamps, handwriting, and uneven lighting, before changing preprocessing defaults.


## Existing technical docs

- [Docker operations](docs/docker.md)
- [OCR wrapper contract](docs/chandra-wrapper.md)
- [OCR wrapper OpenAPI](docs/chandra-wrapper.openapi.yaml)
- [Project status and roadmap](docs/project-status-roadmap.md)
