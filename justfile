set dotenv-load := false

python := ".venv/bin/python"

test:
    {{python}} -m pytest -q

coverage:
    {{python}} -m pytest --cov=app --cov=ocr_adapter --cov-report=term-missing -q

dev-api:
    {{python}} -m uvicorn app.main:app --reload --env-file .env.local --port 8000

dev-ocr:
    OCR_BACKEND_BASE_URL=http://127.0.0.1:9099/v1 {{python}} -m uvicorn ocr_adapter.main:app --reload --env-file .env.local --port 9000
