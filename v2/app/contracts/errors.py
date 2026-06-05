"""Phase 1 error taxonomy."""

from enum import Enum

from pydantic import BaseModel, Field


class ErrorCode(str, Enum):
    USER_INPUT = "USER_INPUT"
    SCHEMA_MISMATCH = "SCHEMA_MISMATCH"
    SQL_VALIDATION = "SQL_VALIDATION"
    SQL_GENERATION = "SQL_GENERATION"
    DB_RUNTIME = "DB_RUNTIME"
    PYTHON_SANDBOX = "PYTHON_SANDBOX"
    INTERNAL = "INTERNAL"


class ErrorDetail(BaseModel):
    code: ErrorCode
    message: str
    retry_count: int = 0
    details: dict = Field(default_factory=dict)
