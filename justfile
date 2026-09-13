set dotenv-load := false

python := ".venv/bin/python"

# Show available recipes.
help:
    just --list

# Run the test suite.
test:
    {{python}} -m pytest -q

# Run tests with coverage.
coverage:
    {{python}} -m pytest --cov=app --cov=ocr_adapter --cov-report=term-missing -q

# Start API and OCR containers. Requires .env.local and the external llm network for Chandra.
start:
    test -f .env.local || (echo "Missing .env.local; copy .env.example first." >&2; exit 1)
    docker compose --env-file .env.local up --detach --build

# Stop API and OCR containers. Leave external Chandra/llamactl services running.
stop:
    test -f .env.local || (echo "Missing .env.local; copy .env.example first." >&2; exit 1)
    docker compose --env-file .env.local down

# Run the API locally with hot reload.
dev-api:
    {{python}} -m uvicorn app.main:app --reload --env-file .env.local --port 8000

# Run the OCR adapter locally with hot reload. Supports Chandra or Textract via .env.local.
dev-ocr:
    OCR_BACKEND_BASE_URL=http://127.0.0.1:9099/v1 {{python}} -m uvicorn ocr_adapter.main:app --reload --env-file .env.local --port 9000
