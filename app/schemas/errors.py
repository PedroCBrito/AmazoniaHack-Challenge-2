from pydantic import BaseModel, ConfigDict


class ErrorDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str


class ApiError(BaseModel):
    model_config = ConfigDict(extra="forbid")

    error: ErrorDetail

