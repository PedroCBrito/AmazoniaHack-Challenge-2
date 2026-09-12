# Docker Deployment

The recommended local deployment uses two containers connected by a private
Compose network:

- `api`: the public FastAPI application on host port `8000`;
- `ocr`: an internal placeholder on container port `9000`.

The placeholder is intentionally unavailable for OCR. Its `/live` endpoint returns
`200`, while `/health` and `/ocr` return `503 model_not_ready`. It preserves the
network boundary without returning fake recognition data. Replace this service
with the real Chandra wrapper when it is implemented.

```mermaid
flowchart LR
    Client[Client] -->|localhost:8000| API[api container]
    API -->|http://ocr:9000| OCR[ocr container]
    OCR -. future .-> Chandra[Chandra runtime]
```

Only the API port is published to the host. The OCR service is reachable by its
Compose DNS name only from containers on the project network.

## Build and run

Requirements:

- Docker Engine with the Compose plugin;
- enough disk and memory for the API images;
- later, compatible GPU/container runtime resources for the selected Chandra
  deployment.

From the repository root:

```bash
docker compose build --pull
docker compose up --detach
docker compose ps
```

Check the API:

```bash
curl http://127.0.0.1:8000/live
curl http://127.0.0.1:8000/health
```

`/live` should report the API process as alive. `/health` reports `degraded` until
the placeholder is replaced by a ready OCR implementation. Swagger UI remains at
<http://127.0.0.1:8000/docs>.

Inspect logs and stop the deployment with:

```bash
docker compose logs --follow
docker compose down
```

## Image targets

The multi-stage `Dockerfile` has two final targets:

| Target | Default process | Published externally |
|---|---|---|
| `api` | `app.main:app` on port `8000` | yes, through Compose |
| `ocr-placeholder` | `ocr_placeholder.main:app` on port `9000` | no |

Building without `--target` produces the API image because `api` is the final
stage:

```bash
docker build --target api -t environmental-document-extraction-api:local .
docker run --rm --init -p 8000:8000 \
  -e APP_CHANDRA_BASE_URL=http://host.docker.internal:9000 \
  environmental-document-extraction-api:local
```

Use Compose for the normal workflow. The standalone command requires a reachable
OCR wrapper at the configured address.

## Security and runtime properties

Both images:

- derive from the official Python slim image;
- install pinned runtime dependencies in a separate build stage;
- run as the unprivileged numeric user and group `10001`;
- use exec-form commands and a 30-second graceful shutdown deadline;
- disable the framework's identifying `Server` response header;
- use a process-only `/live` Docker healthcheck;
- write temporary multipart data only to a size-limited `/tmp` tmpfs in Compose;
- run with a read-only root filesystem, all Linux capabilities dropped, and
  `no-new-privileges` enabled;
- keep application access logs on stdout/stderr for the container log driver.

The base image uses a floating Python patch tag (`python:3.12-slim-bookworm`) so
`docker compose build --pull` receives upstream security fixes. For reproducible
release builds, resolve that tag to an approved digest in CI and pass it as the
global `PYTHON_IMAGE` build argument.

Do not copy `.env`, uploaded images, OCR output, models, Git history, test caches,
or local virtual environments into a build context. `.dockerignore` excludes these
items. Runtime secrets should be injected by the deployment platform and not baked
into an image or committed to the repository.

## Why the services are separate

API traffic and OCR inference have different scaling, memory, startup, GPU, and
failure characteristics. Keeping them in separate containers allows the OCR model
to restart or move to GPU hardware without restarting the API. It also avoids a
process supervisor inside the API image and prevents multiple API workers from
accidentally loading duplicate model copies.

The application still sees a simple HTTP dependency at `http://ocr:9000`.

## Replacing the OCR placeholder

Implement the contract in [`chandra-wrapper.md`](chandra-wrapper.md), then change
only the `ocr` service in `compose.yaml`. For example:

```yaml
services:
  ocr:
    image: registry.example.com/chandra-wrapper:<immutable-version>
    expose:
      - "9000"
    # Add the GPU reservation required by the chosen runtime here.
```

Keep the Compose service name `ocr`, internal port `9000`, and endpoint contract.
The API setting can then remain:

```text
APP_CHANDRA_BASE_URL=http://ocr:9000
```

Do not add a readiness dependency that blocks the API container from starting for
the full model-load duration. The API is useful for liveness and diagnostics while
OCR warms up, and `/health` already reports dependency readiness.

## Dependency policy

`requirements.txt` contains production dependencies only. `requirements-dev.txt`
adds test tools for local development and CI. Versions are pinned so a dependency
update is deliberate and can be validated before rebuilding an image.

The Uvicorn standard extras are intentionally not installed: this API currently
does not need reload watchers, WebSockets, YAML logging configuration, or alternate
HTTP/event-loop implementations in production. The OCR operation is the expected
bottleneck, so the smaller dependency surface is preferable at this stage.

