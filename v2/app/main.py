"""FastAPI entrypoint — Phase 1 stabilization."""

from __future__ import annotations

import os
import time

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from app.config import API_VERSION, PROMPT_VERSIONS
from app.contracts.errors import ErrorCode, ErrorDetail
from app.contracts.clarification import ClarificationPayload
from app.contracts.requests import QueryRequest, resolved_filters_from_request
from app.contracts.responses import (
    QueryResponse,
    TargetResultSummary,
    UsageSummary,
    ValidationSummary,
)
from app.graph import compiled_analyst_graph
from app.insights.grounding import build_multi_target_insight
from app.planning.orchestration import total_row_count
from app.planning.scope_guard import OUT_OF_SCOPE_USER_MESSAGE, is_likely_in_scope
from app.contracts.schema import SchemaExplorerResponse
from app.observability.logging import configure_logging, log_event
from app.observability.metrics import metrics_collector
from app.observability.trace import new_trace_id, set_trace_id
from app.schema.explorer import fetch_live_schema, fetch_table_preview

configure_logging()

app = FastAPI(
    title="ERP Business Data Analyst Agent",
    description="Phase 1: deterministic pipeline, SQL validation, error taxonomy, observability.",
    version=API_VERSION,
)

def _cors_origins() -> list[str]:
    origins = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:4173",
        "http://127.0.0.1:4173",
    ]
    for key in ("FRONTEND_URL", "CORS_ORIGINS"):
        raw = os.getenv(key, "").strip()
        if not raw:
            continue
        for origin in raw.split(","):
            cleaned = origin.strip().rstrip("/")
            if cleaned and cleaned not in origins:
                origins.append(cleaned)
    return origins


app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def trace_middleware(request: Request, call_next):
    trace_id = request.headers.get("X-Trace-Id") or new_trace_id()
    set_trace_id(trace_id)
    request.state.trace_id = trace_id
    response = await call_next(request)
    response.headers["X-Trace-Id"] = trace_id
    return response


def _build_error(
    code: ErrorCode,
    message: str,
    retry_count: int = 0,
    details: dict | None = None,
) -> ErrorDetail:
    return ErrorDetail(
        code=code,
        message=message,
        retry_count=retry_count,
        details=details or {},
    )


def _python_error_is_non_blocking(
    *,
    python_out: dict,
    insight_text: str,
    partial_pipeline: bool,
    has_failed_target: bool,
    row_count: int,
) -> bool:
    """SQL + insight succeeded; optional Python failure should not surface as partial."""
    if not isinstance(python_out, dict) or not python_out.get("error"):
        return False
    if partial_pipeline or has_failed_target:
        return False
    if not insight_text.strip() or row_count <= 0:
        return False
    return True


def _serialize_target_results(state: dict) -> dict[str, TargetResultSummary]:
    raw = state.get("target_results") or {}
    out: dict[str, TargetResultSummary] = {}
    for tid, bundle in raw.items():
        if not isinstance(bundle, dict):
            continue
        rows = bundle.get("rows") or []
        sanitized_rows = []
        for row in rows[:5]:
            if isinstance(row, dict):
                sanitized_rows.append(
                    {k: v for k, v in row.items() if str(k).lower() != "match_score"}
                )
            else:
                sanitized_rows.append(row)
        out[tid] = TargetResultSummary(
            label=bundle.get("label", tid),
            sql=bundle.get("sql", ""),
            row_count=int(bundle.get("row_count", len(rows))),
            status=bundle.get("status", "success"),
            error=bundle.get("error"),
            rows_sample=sanitized_rows,
        )
    return out


def _sql_response_fields(state: dict) -> tuple[str, dict[str, str]]:
    target_results = state.get("target_results") or {}
    if state.get("query_mode") == "MULTI_STEP" and target_results:
        return "", {
            tid: bundle.get("sql", "")
            for tid, bundle in target_results.items()
            if isinstance(bundle, dict)
        }
    return state.get("generated_sql", ""), {}


def _row_count_for_response(state: dict) -> int:
    target_results = state.get("target_results") or {}
    if target_results:
        return total_row_count(target_results)
    return len(state.get("database_results") or [])


def _validation_summary(state: dict) -> ValidationSummary | None:
    raw = state.get("validation_result")
    if not raw:
        return None
    return ValidationSummary(
        passed=raw.get("passed", False),
        syntax_ok=raw.get("syntax_ok", True),
        schema_ok=raw.get("schema_ok", True),
        policy_ok=raw.get("policy_ok", True),
        complexity_score=raw.get("complexity_score", 0),
        issues=raw.get("issues", []),
    )


def _usage_summary(state: dict) -> UsageSummary:
    raw = state.get("usage") or {}
    steps = state.get("usage_steps") or {}
    return UsageSummary(
        llm_prompt_tokens=int(raw.get("llm_prompt_tokens", 0)),
        llm_completion_tokens=int(raw.get("llm_completion_tokens", 0)),
        llm_total_tokens=int(raw.get("llm_total_tokens", 0)),
        rag_embedding_tokens=int(raw.get("rag_embedding_tokens", 0)),
        rag_calls=int(raw.get("rag_calls", 0)),
        db_calls=int(raw.get("db_calls", 0)),
        db_success_calls=int(raw.get("db_success_calls", 0)),
        db_failed_calls=int(raw.get("db_failed_calls", 0)),
        steps={k: {kk: int(vv) for kk, vv in (sv or {}).items()} for k, sv in steps.items()},
    )


@app.get("/health")
async def health():
    return {"status": "ok", "version": API_VERSION}


@app.get("/api/v1/metrics")
async def metrics():
    """Baseline observability snapshot for dashboards."""
    return metrics_collector.snapshot()


@app.get("/api/v1/schema", response_model=SchemaExplorerResponse)
async def get_database_schema(refresh: bool = False):
    """Live Supabase tables, columns, relationships, and row counts."""
    try:
        payload = fetch_live_schema(force_refresh=refresh)
        return SchemaExplorerResponse(**payload, cached=not refresh)
    except Exception as exc:
        log_event("schema_explorer_failed", extra={"error": str(exc)})
        raise HTTPException(
            status_code=503,
            detail={
                "code": "SCHEMA_FETCH_FAILED",
                "message": f"Could not load live database schema: {exc}",
            },
        ) from exc


@app.get("/api/v1/schema/tables/{table_name}/preview")
async def get_table_preview(table_name: str):
    """Live sample rows for a single table."""
    try:
        rows = fetch_table_preview(table_name)
        return {"table_name": table_name, "rows": rows, "limit": len(rows)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        log_event("schema_preview_failed", extra={"table": table_name, "error": str(exc)})
        raise HTTPException(
            status_code=503,
            detail=f"Could not load preview for {table_name}: {exc}",
        ) from exc


@app.post("/api/v1/analyze", response_model=QueryResponse)
async def process_analyst_request(request: Request, payload: QueryRequest):
    trace_id = getattr(request.state, "trace_id", new_trace_id())
    started = time.perf_counter()

    if not payload.query.strip():
        raise HTTPException(
            status_code=400,
            detail=_build_error(
                ErrorCode.USER_INPUT, "Input query cannot be blank."
            ).model_dump(),
        )

    log_event(
        "request_start",
        extra={"query_len": len(payload.query)},
    )

    if not is_likely_in_scope(payload.query):
        log_event("request_out_of_scope", extra={"query_len": len(payload.query)})
        return QueryResponse(
            status="failed",
            trace_id=trace_id,
            execution_category="OUT_OF_SCOPE",
            query_mode="SINGLE",
            insight=OUT_OF_SCOPE_USER_MESSAGE,
            error=_build_error(
                ErrorCode.USER_INPUT,
                "Query is outside ERP business analytics scope.",
            ),
            prompt_versions=PROMPT_VERSIONS,
        )

    initial_state = {
        "user_query": payload.query,
        "resolved_filters": resolved_filters_from_request(payload),
        "current_year": int(time.strftime("%Y")),
        "trace_id": trace_id,
        "retry_count": 0,
        "prompt_versions": PROMPT_VERSIONS,
        "usage": {
            "llm_prompt_tokens": 0,
            "llm_completion_tokens": 0,
            "llm_total_tokens": 0,
            "rag_embedding_tokens": 0,
            "rag_calls": 0,
            "db_calls": 0,
            "db_success_calls": 0,
            "db_failed_calls": 0,
        },
        "usage_steps": {},
    }

    try:
        final_state = compiled_analyst_graph.invoke(initial_state)
    except Exception as exc:
        latency_ms = (time.perf_counter() - started) * 1000
        message = str(exc)
        if "unknown table" in message.lower():
            error_code = ErrorCode.SCHEMA_MISMATCH
            insight = f"Planner target references an invalid table: {message}"
        elif "planner returned invalid json" in message.lower() or (
            "json_invalid" in message.lower() and "planner" in message.lower()
        ):
            error_code = ErrorCode.USER_INPUT
            insight = OUT_OF_SCOPE_USER_MESSAGE
        else:
            error_code = ErrorCode.INTERNAL
            insight = "Internal pipeline failure."
        metrics_collector.record_request(
            status="failed",
            latency_ms=latency_ms,
            error_code=error_code.value,
        )
        log_event("request_failed", extra={"error": message})
        return QueryResponse(
            status="failed",
            trace_id=trace_id,
            insight=insight,
            error=_build_error(error_code, message),
            usage=_usage_summary(initial_state),
            prompt_versions=PROMPT_VERSIONS,
        )

    latency_ms = (time.perf_counter() - started) * 1000

    if final_state.get("out_of_scope"):
        metrics_collector.record_request(
            status="failed",
            latency_ms=latency_ms,
            error_code=ErrorCode.USER_INPUT.value,
        )
        log_event("request_out_of_scope_complete")
        return QueryResponse(
            status="failed",
            trace_id=trace_id,
            execution_category=final_state.get("execution_category", "OUT_OF_SCOPE"),
            query_mode="SINGLE",
            insight=final_state.get("final_insight", OUT_OF_SCOPE_USER_MESSAGE),
            error=_build_error(
                ErrorCode.USER_INPUT,
                "Query is outside ERP business analytics scope.",
            ),
            usage=_usage_summary(final_state),
            prompt_versions=PROMPT_VERSIONS,
        )

    validation = _validation_summary(final_state)
    retry_count = final_state.get("retry_count", 0)
    row_count = _row_count_for_response(final_state)
    query_mode = final_state.get("query_mode", "SINGLE")
    target_summaries = _serialize_target_results(final_state)
    generated_sql, generated_sql_by_target = _sql_response_fields(final_state)

    # Validation exhausted
    if final_state.get("validation_error") and not final_state.get(
        "target_results"
    ) and not final_state.get("database_results"):
        metrics_collector.record_request(
            status="failed",
            latency_ms=latency_ms,
            error_code=final_state.get("error_code", ErrorCode.SQL_VALIDATION.value),
            validation_failed=True,
            retry_count=retry_count,
        )
        return QueryResponse(
            status="failed",
            trace_id=trace_id,
            execution_category=final_state.get("execution_category", ""),
            query_mode=query_mode,
            generated_sql=generated_sql,
            generated_sql_by_target=generated_sql_by_target,
            target_results=target_summaries,
            python_calculations={},
            insight="SQL could not pass validation within retry limits.",
            validation=validation,
            error=_build_error(
                ErrorCode.SQL_VALIDATION,
                final_state["validation_error"],
                retry_count=retry_count,
                details=final_state.get("validation_result", {}),
            ),
            usage=_usage_summary(final_state),
            prompt_versions=PROMPT_VERSIONS,
            retry_count=retry_count,
            row_count=row_count,
        )

    # Database failure
    if final_state.get("sql_error") and not target_summaries:
        metrics_collector.record_request(
            status="failed",
            latency_ms=latency_ms,
            error_code=ErrorCode.DB_RUNTIME.value,
            db_failed=True,
            retry_count=retry_count,
        )
        return QueryResponse(
            status="failed",
            trace_id=trace_id,
            execution_category=final_state.get("execution_category", ""),
            query_mode=query_mode,
            generated_sql=generated_sql,
            generated_sql_by_target=generated_sql_by_target,
            target_results=target_summaries,
            python_calculations={"error": final_state["sql_error"]},
            insight="Database execution failed within retry limits.",
            validation=validation,
            error=_build_error(
                ErrorCode.DB_RUNTIME,
                final_state["sql_error"],
                retry_count=retry_count,
            ),
            usage=_usage_summary(final_state),
            prompt_versions=PROMPT_VERSIONS,
            retry_count=retry_count,
            row_count=row_count,
        )

    if final_state.get("needs_clarification"):
        clarification_raw = final_state.get("clarification") or {}
        clarification = (
            ClarificationPayload.model_validate(clarification_raw)
            if clarification_raw
            else None
        )
        insight_text = final_state.get("final_insight") or (
            clarification.message if clarification else ""
        )
        metrics_collector.record_request(
            status="needs_clarification",
            latency_ms=latency_ms,
            retry_count=retry_count,
        )
        log_event(
            "request_needs_clarification",
            extra={"row_count": row_count, "parameter": getattr(clarification, "parameter", "")},
        )
        return QueryResponse(
            status="needs_clarification",
            trace_id=trace_id,
            execution_category=final_state.get("execution_category", ""),
            query_mode=query_mode,
            generated_sql=generated_sql,
            generated_sql_by_target=generated_sql_by_target,
            target_results=target_summaries,
            python_calculations=final_state.get("python_output", {}),
            insight=insight_text,
            clarification=clarification,
            validation=validation,
            usage=_usage_summary(final_state),
            prompt_versions=PROMPT_VERSIONS,
            retry_count=retry_count,
            row_count=row_count,
        )

    python_out = final_state.get("python_output", {})
    status = "success"
    error_detail = None
    insight_text = final_state.get("final_insight", "")

    partial_pipeline = bool(
        final_state.get("pipeline_partial")
        or final_state.get("validation_error")
        or final_state.get("sql_error")
    )
    has_failed_target = any(
        t.status == "failed" for t in target_summaries.values()
    )
    planned_count = len(final_state.get("targets") or [])
    completed_count = len(target_summaries)

    if partial_pipeline or has_failed_target or (
        query_mode == "MULTI_STEP" and planned_count > completed_count
    ):
        status = "partial"

    if final_state.get("validation_error") and target_summaries:
        error_detail = _build_error(
            ErrorCode.SQL_VALIDATION,
            final_state["validation_error"],
            retry_count=retry_count,
            details=final_state.get("validation_result", {}),
        )
    elif final_state.get("sql_error"):
        error_detail = _build_error(ErrorCode.DB_RUNTIME, final_state["sql_error"])
    elif isinstance(python_out, dict) and python_out.get("error"):
        if not _python_error_is_non_blocking(
            python_out=python_out,
            insight_text=insight_text,
            partial_pipeline=partial_pipeline,
            has_failed_target=has_failed_target,
            row_count=row_count,
        ):
            status = "partial"
            error_detail = _build_error(
                ErrorCode.PYTHON_SANDBOX,
                python_out["error"],
            )
    elif has_failed_target:
        error_detail = _build_error(
            ErrorCode.SQL_VALIDATION,
            "One or more targets failed; see target_results.",
        )

    if not insight_text and query_mode == "MULTI_STEP" and (
        target_summaries or final_state.get("targets")
    ):
        insight_text = build_multi_target_insight(
            payload.query,
            final_state.get("target_results") or {},
            planned_targets=final_state.get("targets"),
        )

    metrics_collector.record_request(
        status=status,
        latency_ms=latency_ms,
        retry_count=retry_count,
    )
    log_event("request_complete", extra={"status": status, "row_count": row_count})

    return QueryResponse(
        status=status,
        trace_id=trace_id,
        execution_category=final_state.get("execution_category", ""),
        query_mode=query_mode,
        generated_sql=generated_sql,
        generated_sql_by_target=generated_sql_by_target,
        target_results=target_summaries,
        python_calculations=python_out,
        insight=insight_text,
        validation=validation,
        error=error_detail,
        usage=_usage_summary(final_state),
        prompt_versions=PROMPT_VERSIONS,
        retry_count=retry_count,
        row_count=row_count,
    )
