from fastapi import APIRouter, File, Request, UploadFile

from app.schemas.errors import ApiError
from app.schemas.extraction import ExtractionResult
from app.schemas.health import HealthResponse, LivenessResponse


router = APIRouter()


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
        502: {"model": ApiError, "description": "Invalid dependency response"},
        503: {"model": ApiError, "description": "Required service unavailable"},
        504: {"model": ApiError, "description": "Processing deadline exceeded"},
    },
    summary="Extract structured fields from one document image",
)
async def extract(
    request: Request,
    image: UploadFile = File(description="One JPEG or PNG document image"),
) -> ExtractionResult:
    return await request.app.state.extraction_service.extract(image)
