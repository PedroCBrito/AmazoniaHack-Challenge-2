from fastapi import APIRouter, File, HTTPException, Path, Query, Request, UploadFile

from app.schemas.errors import ApiError
from app.schemas.extraction import ExtractionResult
from app.schemas.health import HealthResponse, LivenessResponse
from app.schemas.documents import DocumentDetail, DocumentList
from app.services.ocr_store import OCRStorageError
from app.core.errors import ApplicationError


router = APIRouter()


@router.get("/documents", response_model=DocumentList, summary="List documents stored in SQLite")
async def documents(
    request: Request, limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> DocumentList:
    try:
        return await request.app.state.ocr_store.list_documents(limit, offset)
    except OCRStorageError as exc:
        raise ApplicationError(500, "document_storage_failed", "Could not load documents.") from exc


@router.get("/documents/{document_id}", response_model=DocumentDetail, response_model_by_alias=True)
async def document(request: Request, document_id: int = Path(ge=1)) -> DocumentDetail:
    try:
        stored = await request.app.state.ocr_store.get_document(document_id)
    except OCRStorageError as exc:
        raise ApplicationError(500, "document_storage_failed", "Could not load document.") from exc
    if stored is None:
        raise HTTPException(status_code=404)
    return stored


@router.get(
    "/live",
    response_model=LivenessResponse,
    summary="Report application process liveness",
)
async def live() -> LivenessResponse:
    return LivenessResponse()


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Report application and OCR readiness",
)
async def health(request: Request) -> HealthResponse:
    ocr_ready = await request.app.state.ocr_client.health()
    return HealthResponse(
        status="ok" if ocr_ready else "degraded",
        service="ready",
        dependencies={"ocr": "ready" if ocr_ready else "unavailable"},
    )


@router.post(
    "/extract",
    response_model=ExtractionResult,
    response_model_by_alias=True,
    responses={
        413: {"model": ApiError, "description": "Image limit exceeded"},
        415: {"model": ApiError, "description": "Unsupported image format"},
        422: {"model": ApiError, "description": "Invalid image or request"},
        429: {"model": ApiError, "description": "Processing capacity reached"},
        500: {"model": ApiError, "description": "OCR persistence failure"},
        502: {"model": ApiError, "description": "Invalid dependency response"},
        503: {"model": ApiError, "description": "Required service unavailable"},
        504: {"model": ApiError, "description": "Processing deadline exceeded"},
    },
    summary="Extract structured fields from one document image",
    description=(
        "Validates and orients a JPEG/PNG, cleans it with OpenCV when enabled, "
        "then sends it to OCR and field mapping. Results require human review."
    ),
)
async def extract(
    request: Request,
    image: UploadFile = File(description="One JPEG or PNG document image"),
) -> ExtractionResult:
    return await request.app.state.extraction_service.extract(image)
