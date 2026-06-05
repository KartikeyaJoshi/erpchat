"""Structured planner output contract."""

from typing import Literal

from pydantic import BaseModel, Field

from app.contracts.targets import QueryMode, QueryTarget


class PlannerOutput(BaseModel):
    category: Literal["DIRECT_QUERY", "COMPLEX_ANALYSIS", "OUT_OF_SCOPE"]
    query_mode: QueryMode = "SINGLE"
    targets: list[QueryTarget] = Field(default_factory=list)
    steps: list[str] = Field(..., min_length=1)
