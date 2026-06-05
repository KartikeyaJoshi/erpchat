"""API response contracts (Phase 1)."""

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

from app.contracts.clarification import ClarificationPayload
from app.contracts.errors import ErrorDetail


class ValidationSummary(BaseModel):
    passed: bool
    syntax_ok: bool = True
    schema_ok: bool = True
    policy_ok: bool = True
    complexity_score: int = 0
    issues: list[str] = Field(default_factory=list)


class TargetResultSummary(BaseModel):
    label: str = ""
    sql: str = ""
    row_count: int = 0
    status: Literal["success", "failed"] = "success"
    error: Optional[str] = None
    rows_sample: list[dict[str, Any]] = Field(default_factory=list)


class UsageSummary(BaseModel):
    llm_prompt_tokens: int = 0
    llm_completion_tokens: int = 0
    llm_total_tokens: int = 0
    rag_embedding_tokens: int = 0
    rag_calls: int = 0
    db_calls: int = 0
    db_success_calls: int = 0
    db_failed_calls: int = 0
    steps: dict[str, dict[str, int]] = Field(default_factory=dict)


class QueryResponse(BaseModel):
    status: Literal["success", "failed", "partial", "needs_clarification"]
    trace_id: str
    execution_category: str = ""
    query_mode: Literal["SINGLE", "MULTI_STEP"] = "SINGLE"
    generated_sql: str = ""
    generated_sql_by_target: dict[str, str] = Field(default_factory=dict)
    target_results: dict[str, TargetResultSummary] = Field(default_factory=dict)
    python_calculations: dict[str, Any] = Field(default_factory=dict)
    insight: str = ""
    entity_match_notes: list[str] = Field(
        default_factory=list,
        description="Fair-match disclaimers, e.g. matched MUMBAI-WH1 from user phrase.",
    )
    clarification: Optional[ClarificationPayload] = None
    validation: Optional[ValidationSummary] = None
    error: Optional[ErrorDetail] = None
    usage: UsageSummary = Field(default_factory=UsageSummary)
    prompt_versions: dict[str, str] = Field(default_factory=dict)
    retry_count: int = 0
    row_count: int = 0
