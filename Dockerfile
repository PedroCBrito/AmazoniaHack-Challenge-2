# syntax=docker/dockerfile:1.7

ARG PYTHON_IMAGE=python:3.12-slim-bookworm

FROM ${PYTHON_IMAGE} AS dependencies

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN python -m venv /opt/venv

COPY requirements.txt /tmp/requirements.txt

RUN /opt/venv/bin/python -m pip install --requirement /tmp/requirements.txt \
    && /opt/venv/bin/python -m compileall -q /opt/venv


FROM ${PYTHON_IMAGE} AS runtime

ARG APP_VERSION=0.1.0

LABEL org.opencontainers.image.title="Environmental Document Extraction API" \
      org.opencontainers.image.description="Review-oriented environmental document extraction service" \
      org.opencontainers.image.version="${APP_VERSION}"

ENV PATH="/opt/venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    APP_ENVIRONMENT=production

RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --no-create-home \
        --home-dir /nonexistent --shell /usr/sbin/nologin app

COPY --from=dependencies /opt/venv /opt/venv

WORKDIR /srv/application
USER 10001:10001


# OCR adapter delegates inference to a local or remote OpenAI-compatible backend.
FROM runtime AS ocr-adapter

LABEL org.opencontainers.image.title="Chandra OCR Adapter" \
      org.opencontainers.image.description="Private adapter for OpenAI-compatible Chandra inference"

COPY --chown=10001:10001 ocr_adapter ./ocr_adapter

EXPOSE 9000

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:9000/live', timeout=2).read()"]

STOPSIGNAL SIGTERM

CMD ["python", "-m", "uvicorn", "ocr_adapter.main:app", "--host", "0.0.0.0", "--port", "9000", "--lifespan", "on", "--no-server-header", "--timeout-graceful-shutdown", "30"]


# The API is the final/default image target.
FROM runtime AS api

ENV APP_CHANDRA_BASE_URL=http://ocr:9000

COPY --chown=10001:10001 app ./app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/live', timeout=2).read()"]

STOPSIGNAL SIGTERM

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--lifespan", "on", "--no-server-header", "--timeout-graceful-shutdown", "30"]
