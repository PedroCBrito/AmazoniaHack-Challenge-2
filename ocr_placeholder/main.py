from typing import Annotated, Literal

from fastapi import FastAPI, File, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LivenessResponse(StrictModel):
    status: Literal["alive"] = "alive"
    service: Literal["ocr-placeholder"] = "ocr-placeholder"


class ErrorDetail(StrictModel):
    code: str
    message: str


class ErrorResponse(StrictModel):
    error: ErrorDetail


MODEL_NOT_READY = ErrorResponse(
    error=ErrorDetail(
        code="model_not_ready",
        message="The Chandra OCR service has not been implemented yet.",
    )
)


app = FastAPI(
    title="Chandra OCR Wrapper Placeholder",
    version="0.1.0",
    description=(
        "Temporary service that preserves the OCR network contract and always "
        "reports the model as unavailable."
    ),
)


@app.get("/live", response_model=LivenessResponse)
async def live() -> LivenessResponse:
    return LivenessResponse()


@app.get(
    "/health",
    status_code=503,
    response_model=ErrorResponse,
    description="The placeholder is never ready to perform OCR.",
)
async def health() -> JSONResponse:
    return JSONResponse(status_code=503, content=MODEL_NOT_READY.model_dump())


@app.post(
    "/ocr",
    status_code=503,
    response_model=ErrorResponse,
    description="The placeholder never returns simulated OCR content.",
)
async def recognize(
    image: Annotated[UploadFile, File(description="One JPEG or PNG image")],
) -> JSONResponse:
    await image.close()
    return JSONResponse(status_code=503, content=MODEL_NOT_READY.model_dump())
