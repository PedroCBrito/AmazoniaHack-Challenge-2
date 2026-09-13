# Environmental Document Extraction

FastAPI service that turns photographed environmental documents into reviewable structured JSON. OCR backends are interchangeable: use local GPU-hosted Chandra or remote Amazon Textract.

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

## Current status

The API, OCR adapter, Chandra backend, and Textract backend are implemented. Field mapping remains pending, so `/extract` returns null mapped fields with an explicit warning until a mapper is configured.

## Existing technical docs

- [Docker operations](docs/docker.md)
- [OCR wrapper contract](docs/chandra-wrapper.md)
- [OCR wrapper OpenAPI](docs/chandra-wrapper.openapi.yaml)
- [Project status and roadmap](docs/project-status-roadmap.md)
