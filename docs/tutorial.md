# Tutorial: run the service

This tutorial starts the API and OCR adapter with Docker. It assumes Docker Compose, an external `llm` network, and a running Chandra-compatible backend.

## Configure

```bash
cp .env.example .env.local
```

Keep `OCR_PROVIDER=chandra` for local Chandra. For Textract setup, follow [How-to: use Textract](how-to.md#use-textract-with-dev-ocr).

## Start

```bash
just start
```

Check the services:

```bash
curl http://127.0.0.1:8000/live
curl http://127.0.0.1:8000/health
```

Open <http://127.0.0.1:8000/docs> for interactive API documentation.

## Process one image

```bash
curl --fail-with-body --max-time 180 \
  -F image=@path/to/document.jpg \
  http://127.0.0.1:8000/extract
```

Stop the API and adapter with:

```bash
just stop
```
