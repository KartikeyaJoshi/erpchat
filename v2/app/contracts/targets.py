"""Multi-step query target contracts (Option B)."""

from typing import Literal

from pydantic import BaseModel, Field


class QueryTarget(BaseModel):
    id: str = Field(..., min_length=1, pattern=r"^[a-z][a-z0-9_]*$")
    label: str = Field(..., min_length=1)
    tables: list[str] = Field(default_factory=list)
    intent: str = Field(..., min_length=1)


QueryMode = Literal["SINGLE", "MULTI_STEP"]


class TargetExecutionBundle(BaseModel):
    label: str
    sql: str = ""
    rows: list[dict] = Field(default_factory=list)
    row_count: int = 0
    status: Literal["success", "failed"] = "success"
    error: str | None = None
