"""LangGraph worker nodes (Phase 1 + multi-step orchestration)."""

from __future__ import annotations

import hashlib
import json
import os
import re
import time

import pandas as pd
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_groq import ChatGroq
from pydantic import ValidationError

from app.config import (
    GROQ_MODEL_ID,
    LLM_TEMPERATURE,
    MAX_SQL_RETRIES_PER_TARGET,
    PROMPT_VERSIONS,
    SQL_ROW_LIMIT,
)
from app.contracts.errors import ErrorCode
from app.contracts.planner import PlannerOutput
from app.database import supabase_client
from app.insights.grounding import (
    extract_verified_facts,
    sanitize_insight_text,
    try_blocked_ambiguous_entity_insight,
    try_deterministic_insight,
    try_empty_rows_insight,
    try_multi_target_insight,
)
from app.insights.row_sanitize import sanitize_rows_for_insight
from app.planning.entity_extract_gate import (
    is_entity_spec_allowed,
    should_skip_entity_extractor,
)
from app.observability.logging import NodeTimer, log_event
from app.planning.attribute_lookup import (
    expects_single_entity_answer,
    try_attribute_lookup_sql,
)
from app.planning.disambiguation import (
    build_resolved_entity_sql,
    evaluate_disambiguation,
)
from app.planning.python_bypass import should_bypass_python_analyzer
from app.planning.orchestration import (
    current_target_from_state,
    get_execution_targets,
    normalize_planner_output,
    targets_to_state_dicts,
)
from app.planning.scope_guard import (
    OUT_OF_SCOPE_USER_MESSAGE,
    is_likely_in_scope,
    is_planner_parse_failure_out_of_scope,
)
from app.prompts import (
    INSIGHT_SYNTHESIZER_SYSTEM_PROMPT,
    PLANNER_SYSTEM_PROMPT,
    PYTHON_ANALYZER_SYSTEM_PROMPT,
    SQL_GENERATOR_SYSTEM_PROMPT,
)
from app.planning.entity_extractor import extract_entity_filter
from app.rag import get_schema_context
from app.schema.loader import allowed_tables
from app.sql.target_templates import resolve_ad_hoc_template_sql, resolve_template_sql
from app.sql.entity_match_sql import EntityFilterSpec, build_entity_match_sql
from app.state import AnalystState
from app.validator.sql_validator import normalize_sql_for_execution, validate_sql

load_dotenv()

if not os.getenv("GROQ_API_KEY"):
    raise ValueError("CRITICAL ERROR: GROQ_API_KEY is missing from environment.")

llm_engine = ChatGroq(model=GROQ_MODEL_ID, temperature=LLM_TEMPERATURE)


def _strip_json_markdown(text: str) -> str:
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned.strip()


def _strip_sql_markdown(text: str) -> str:
    clean_sql = text.strip().replace("```sql", "").replace("```", "").strip()
    if ";" in clean_sql:
        clean_sql = clean_sql.split(";")[0].strip()
    if clean_sql.startswith("'") and clean_sql.endswith("'"):
        clean_sql = clean_sql[1:-1].strip()
    elif clean_sql.startswith('"') and clean_sql.endswith('"'):
        clean_sql = clean_sql[1:-1].strip()
    return clean_sql


def _extract_warehouse_phrase(query: str) -> str | None:
    cleaned = re.sub(r"\s+", " ", query).strip().rstrip("?!.")
    patterns = [
        r"\b(?:in|at|for)\s+([A-Za-z0-9\- ]+?)\s+warehouse\b",
        r"\b(?:in|at|for)\s+([A-Za-z0-9\- ]+)$",
        r"\b([A-Za-z0-9\- ]+?)\s+warehouse\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, cleaned, flags=re.IGNORECASE)
        if not match:
            continue
        phrase = (match.group(1) or "").strip()
        phrase = re.sub(r"\b(?:how many|total|items?|current|stock|level|there|are|is|what)\b", "", phrase, flags=re.IGNORECASE).strip()
        if phrase:
            if "warehouse" not in phrase.lower():
                phrase = f"{phrase} Warehouse"
            return phrase
    return None


def _warehouse_fuzzy_fallback_spec(user_query: str) -> EntityFilterSpec | None:
    lower = user_query.lower()
    if "warehouse" not in lower:
        return None
    if not any(token in lower for token in ("stock", "items", "inventory", "level")):
        return None
    phrase = _extract_warehouse_phrase(user_query)
    if not phrase:
        return None
    return EntityFilterSpec(
        query_kind="warehouse_stock",
        parameter="warehouse_name",
        table="inventory",
        column="warehouse_name",
        phrase=phrase,
    )


def _base_usage() -> dict[str, int]:
    return {
        "llm_prompt_tokens": 0,
        "llm_completion_tokens": 0,
        "llm_total_tokens": 0,
        "rag_embedding_tokens": 0,
        "rag_calls": 0,
        "db_calls": 0,
        "db_success_calls": 0,
        "db_failed_calls": 0,
    }


def _base_step_usage() -> dict[str, dict[str, int]]:
    return {}


def _merge_usage(state: AnalystState, delta: dict[str, int] | None = None) -> dict[str, int]:
    usage = dict(state.get("usage") or _base_usage())
    for key, value in (delta or {}).items():
        usage[key] = int(usage.get(key, 0)) + int(value or 0)
    return usage


def _merge_step_usage(
    state: AnalystState,
    step: str,
    delta: dict[str, int] | None = None,
) -> dict[str, dict[str, int]]:
    steps = dict(state.get("usage_steps") or _base_step_usage())
    current = dict(steps.get(step) or {})
    for key, value in (delta or {}).items():
        current[key] = int(current.get(key, 0)) + int(value or 0)
    steps[step] = current
    return steps


def _llm_usage_delta(response: object) -> dict[str, int]:
    md = getattr(response, "response_metadata", None) or {}
    token_usage = md.get("token_usage", {}) if isinstance(md, dict) else {}
    um = getattr(response, "usage_metadata", None) or {}
    prompt = token_usage.get("prompt_tokens", 0) or md.get("prompt_tokens", 0) or um.get("input_tokens", 0)
    completion = token_usage.get("completion_tokens", 0) or md.get("completion_tokens", 0) or um.get("output_tokens", 0)
    total = token_usage.get("total_tokens", 0) or md.get("total_tokens", 0) or um.get("total_tokens", 0)
    return {
        "llm_prompt_tokens": int(prompt or 0),
        "llm_completion_tokens": int(completion or 0),
        "llm_total_tokens": int(total or ((prompt or 0) + (completion or 0))),
    }


def _feedback_block(state: AnalystState) -> str:
    parts = []
    current = current_target_from_state(state)
    if current:
        parts.append(f"[CURRENT TARGET: {current.id}] {current.label}")
    if state.get("validation_error"):
        parts.append(
            f"[VALIDATION FAILURE]\n{state['validation_error']}\n"
            f"Details: {state.get('validation_result', {})}"
        )
        err = state["validation_error"].lower()
        if "unknown table" in err:
            parts.append(
                f"REMEDIATION: Use ONLY these physical tables: {', '.join(sorted(allowed_tables()))}. "
                "For CTEs use WITH cte_name AS (SELECT ...) then SELECT ... FROM cte_name. "
                "Never reference top_products or other invented table names."
            )
    if state.get("sql_error"):
        parts.append(f"[DATABASE ERROR]\n{state['sql_error']}")
    return "\n\n".join(parts)


def _finalize_target_failure(
    state: AnalystState,
    message: str,
    result_dict: dict,
    *,
    error_code: str = ErrorCode.SQL_VALIDATION.value,
) -> dict:
    """Record failed target and stop further SQL targets; allow partial insight."""
    current = current_target_from_state(state)
    target_results = dict(state.get("target_results") or {})
    targets = state.get("targets") or []

    if current:
        target_results[current.id] = {
            "label": current.label,
            "sql": state.get("generated_sql", ""),
            "rows": [],
            "row_count": 0,
            "status": "failed",
            "error": message,
        }

    return {
        "target_results": target_results,
        "current_target_index": len(targets),
        "validation_error": message,
        "validation_result": result_dict,
        "error_code": error_code,
        "pipeline_partial": True,
        "retry_count": state.get("retry_count", 0) + 1,
    }


def _out_of_scope_state() -> dict:
    return {
        "out_of_scope": True,
        "execution_category": "OUT_OF_SCOPE",
        "query_mode": "SINGLE",
        "logical_plan": [],
        "targets": [],
        "current_target_index": 0,
        "target_results": {},
        "retry_count": 0,
        "final_insight": OUT_OF_SCOPE_USER_MESSAGE,
        "error_code": ErrorCode.USER_INPUT.value,
        "prompt_versions": PROMPT_VERSIONS,
        "usage": _base_usage(),
        "usage_steps": _base_step_usage(),
    }


def planner_node(state: AnalystState) -> dict:
    with NodeTimer("planner", {"prompt_version": PROMPT_VERSIONS["planner"]}):
        user_query = state["user_query"]

        if not is_likely_in_scope(user_query):
            log_event("query_out_of_scope_heuristic", "planner")
            return _out_of_scope_state()

        year = state.get("current_year", int(time.strftime("%Y")))
        ctx = get_schema_context(user_query)
        formatted = PLANNER_SYSTEM_PROMPT.format(
            current_year=year,
            schema_context=ctx.schema_context,
            metric_definitions=ctx.metric_definitions,
        )
        messages = [
            SystemMessage(content=formatted),
            HumanMessage(content=user_query),
        ]
        response = llm_engine.invoke(messages)
        usage = _merge_usage(
            state,
            {
                **_llm_usage_delta(response),
                "rag_calls": 1,
                "rag_embedding_tokens": int(ctx.embedding_tokens),
            },
        )
        usage_steps = _merge_step_usage(
            state,
            "planner",
            {
                **_llm_usage_delta(response),
                "rag_calls": 1,
                "rag_embedding_tokens": int(ctx.embedding_tokens),
            },
        )
        raw = _strip_json_markdown(response.content)

        try:
            parsed = PlannerOutput.model_validate_json(raw)
        except (ValidationError, json.JSONDecodeError) as exc:
            if is_planner_parse_failure_out_of_scope(raw, user_query):
                log_event(
                    "planner_out_of_scope_prose",
                    "planner",
                    extra={"error": str(exc)},
                )
                return _out_of_scope_state()
            log_event("planner_parse_failed", "planner", extra={"error": str(exc)})
            raise ValueError(f"Planner returned invalid JSON: {exc}") from exc

        parsed = normalize_planner_output(parsed, user_query)

        if parsed.category == "OUT_OF_SCOPE":
            log_event("planner_out_of_scope_category", "planner")
            return _out_of_scope_state()
        execution_targets = get_execution_targets(parsed, state["user_query"])

        log_event(
            "plan_complete",
            "planner",
            extra={
                "query_mode": parsed.query_mode,
                "target_count": len(execution_targets),
            },
        )

        return {
            "execution_category": parsed.category,
            "logical_plan": parsed.steps,
            "query_mode": parsed.query_mode,
            "targets": targets_to_state_dicts(execution_targets),
            "current_target_index": 0,
            "target_results": {},
            "retry_count": 0,
            "prompt_versions": PROMPT_VERSIONS,
            "usage": usage,
            "usage_steps": usage_steps,
        }


def sql_generator_node(state: AnalystState) -> dict:
    with NodeTimer("sql_generator", {"prompt_version": PROMPT_VERSIONS["sql_generator"]}):
        feedback = _feedback_block(state)
        year = int(state["current_year"])
        current = current_target_from_state(state)
        usage_delta: dict[str, int] = {}

        template_sql = resolve_template_sql(current, year)

        resolved_filters = dict(state.get("resolved_filters") or {})
        if not template_sql:
            resolved_sql = build_resolved_entity_sql(
                state["user_query"],
                resolved_filters,
                state.get("generated_sql"),
            )
            if resolved_sql:
                return {
                    "generated_sql": resolved_sql,
                    "validation_error": "",
                    "sql_error": "",
                    "usage": _merge_usage(state, usage_delta),
                }
        if not template_sql and (not current or current.id == "primary"):
            attr_sql = try_attribute_lookup_sql(
                state["user_query"],
                resolved_filters,
            )
            if attr_sql:
                log_event(
                    "sql_attribute_lookup_template",
                    "sql_generator",
                    extra={"query_len": len(state["user_query"])},
                )
                return {
                    "generated_sql": attr_sql,
                    "validation_error": "",
                    "sql_error": "",
                    "usage": _merge_usage(state, usage_delta),
                }
        if not template_sql and (not current or current.id == "primary"):
            template_sql = resolve_ad_hoc_template_sql(state["user_query"], year)
        if template_sql:
            log_event(
                "sql_template_used",
                "sql_generator",
                extra={"target_id": current.id if current else None},
            )
            return {
                "generated_sql": template_sql,
                "validation_error": "",
                "sql_error": "",
                "usage": _merge_usage(state, usage_delta),
                "usage_steps": _merge_step_usage(state, "sql_generator", usage_delta),
            }
        if not template_sql and (not current or current.id == "primary"):
            tables_list = list(current.tables) if current and current.tables else None
            intent = current.intent if current else None
            skip_entity_extract = should_skip_entity_extractor(state["user_query"])
            if skip_entity_extract:
                log_event(
                    "entity_extract_skipped",
                    "sql_generator",
                    extra={"reason": "employee_or_measure_lookup"},
                )
            else:
                entity_ctx = get_schema_context(
                    state["user_query"],
                    intent=intent,
                    tables=tables_list,
                )
                entity_spec, extract_usage = extract_entity_filter(
                    llm=llm_engine,
                    user_query=state["user_query"],
                    schema_context=entity_ctx.schema_context,
                    metric_definitions=entity_ctx.metric_definitions,
                )
                usage_delta = {
                    **extract_usage,
                    "rag_calls": 1,
                    "rag_embedding_tokens": int(entity_ctx.embedding_tokens),
                }
                if entity_spec and not is_entity_spec_allowed(
                    state["user_query"], entity_spec
                ):
                    log_event(
                        "entity_extract_gated",
                        "sql_generator",
                        extra={
                            "query_kind": entity_spec.query_kind,
                            "table": entity_spec.table,
                            "phrase": entity_spec.phrase,
                        },
                    )
                    entity_spec = None
                if entity_spec:
                    try:
                        template_sql = build_entity_match_sql(
                            entity_spec,
                            resolved_filters=resolved_filters,
                        )
                        log_event(
                            "sql_entity_match_template",
                            "sql_generator",
                            extra={
                                "query_kind": entity_spec.query_kind,
                                "parameter": entity_spec.parameter,
                                "phrase": entity_spec.phrase,
                            },
                        )
                        return {
                            "generated_sql": template_sql,
                            "validation_error": "",
                            "sql_error": "",
                            "entity_filter_parameter": entity_spec.parameter,
                            "entity_filter_phrase": entity_spec.phrase,
                            "entity_filter_value_column": entity_spec.column,
                            "usage": _merge_usage(
                                state,
                                usage_delta,
                            ),
                            "usage_steps": _merge_step_usage(
                                state, "entity_extractor", usage_delta
                            ),
                        }
                    except ValueError as exc:
                        log_event(
                            "sql_entity_match_invalid_spec",
                            "sql_generator",
                            extra={
                                "error": str(exc),
                                "query_kind": entity_spec.query_kind,
                                "parameter": entity_spec.parameter,
                                "table": entity_spec.table,
                                "column": entity_spec.column,
                            },
                        )
                elif not skip_entity_extract and _warehouse_fuzzy_fallback_spec(
                    state["user_query"]
                ):
                    entity_spec = _warehouse_fuzzy_fallback_spec(state["user_query"])
                    if entity_spec:
                        template_sql = build_entity_match_sql(
                            entity_spec,
                            resolved_filters=resolved_filters,
                        )
                        log_event(
                            "sql_entity_match_heuristic_fallback",
                            "sql_generator",
                            extra={"phrase": entity_spec.phrase},
                        )
                        return {
                            "generated_sql": template_sql,
                            "validation_error": "",
                            "sql_error": "",
                            "entity_filter_parameter": entity_spec.parameter,
                            "entity_filter_phrase": entity_spec.phrase,
                            "entity_filter_value_column": entity_spec.column,
                            "usage": _merge_usage(
                                state,
                                usage_delta,
                            ),
                            "usage_steps": _merge_step_usage(
                                state, "entity_extractor", usage_delta
                            ),
                        }

        tables_list = list(current.tables) if current and current.tables else None
        search_query = state["user_query"]
        intent = current.intent if current else None
        ctx = get_schema_context(
            search_query,
            intent=intent,
            tables=tables_list,
        )

        system_instructions = SQL_GENERATOR_SYSTEM_PROMPT.format(
            schema_context=ctx.schema_context,
            metric_definitions=ctx.metric_definitions,
            current_year=year,
            next_year=year + 1,
            row_limit=SQL_ROW_LIMIT,
        )

        target_block = ""
        if current:
            tables = ", ".join(current.tables) if current.tables else "(infer from schema)"
            target_block = (
                f"\n--- CURRENT TARGET (answer ONLY this part) ---\n"
                f"Target ID: {current.id}\n"
                f"Label: {current.label}\n"
                f"Tables to use: {tables}\n"
                f"Intent: {current.intent}\n"
                f"--- END TARGET ---\n"
            )

        prompt_payload = (
            f"Full User Query (context only): {state['user_query']}\n"
            f"{target_block}"
            f"Execution Plan: {state['logical_plan']}\n"
            f"{feedback}"
        )
        messages = [
            SystemMessage(content=system_instructions),
            HumanMessage(content=prompt_payload),
        ]
        response = llm_engine.invoke(messages)
        usage = _merge_usage(
            state,
            {
                **_llm_usage_delta(response),
                "rag_calls": 1,
                "rag_embedding_tokens": int(ctx.embedding_tokens),
                **usage_delta,
            },
        )
        clean_sql = _strip_sql_markdown(response.content)

        sql_hash = hashlib.sha256(clean_sql.encode()).hexdigest()[:16]
        log_event(
            "sql_generated",
            "sql_generator",
            extra={
                "sql_hash": sql_hash,
                "target_id": current.id if current else "primary",
                "retry_count": state.get("retry_count", 0),
            },
        )
        return {
            "generated_sql": clean_sql,
            "validation_error": "",
            "sql_error": "",
            "usage": usage,
            "usage_steps": _merge_step_usage(
                state,
                "sql_generator",
                {
                    **_llm_usage_delta(response),
                    "rag_calls": 1,
                    "rag_embedding_tokens": int(ctx.embedding_tokens),
                    **usage_delta,
                },
            ),
        }


def sql_validator_node(state: AnalystState) -> dict:
    with NodeTimer("sql_validator"):
        sql = state.get("generated_sql", "")
        result = validate_sql(sql)
        current = current_target_from_state(state)
        log_event(
            "sql_validated",
            "sql_validator",
            extra={
                "passed": result.passed,
                "target_id": current.id if current else None,
                "complexity_score": result.complexity_score,
                "issue_count": len(result.issues),
            },
        )

        if result.passed:
            try:
                executable_sql = normalize_sql_for_execution(sql)
            except ValueError as exc:
                retries = state.get("retry_count", 0) + 1
                if retries > MAX_SQL_RETRIES_PER_TARGET:
                    return _finalize_target_failure(state, str(exc), result.to_dict())
                return {
                    "validation_result": result.to_dict(),
                    "validation_error": str(exc),
                    "error_code": ErrorCode.SQL_VALIDATION.value,
                    "retry_count": retries,
                }
            return {
                "validation_result": result.to_dict(),
                "validation_error": "",
                "generated_sql": executable_sql,
            }

        issue_text = "; ".join(result.issues)
        retries = state.get("retry_count", 0) + 1
        if retries > MAX_SQL_RETRIES_PER_TARGET:
            return _finalize_target_failure(
                state,
                issue_text,
                result.to_dict(),
                error_code=result.error_code or ErrorCode.SQL_VALIDATION.value,
            )
        return {
            "validation_result": result.to_dict(),
            "validation_error": issue_text,
            "error_code": result.error_code or ErrorCode.SQL_VALIDATION.value,
            "retry_count": retries,
        }


def database_executor_node(state: AnalystState) -> dict:
    with NodeTimer("database_executor"):
        current = current_target_from_state(state)
        target_sql = state["generated_sql"]
        targets = state.get("targets") or []
        idx = state.get("current_target_index", 0)
        target_results = dict(state.get("target_results") or {})

        try:
            execution_response = supabase_client.rpc(
                "execute_raw_sql",
                {"query_text": target_sql},
            ).execute()
            rows = execution_response.data or []
            log_event(
                "db_success",
                "database_executor",
                extra={
                    "row_count": len(rows),
                    "target_id": current.id if current else "primary",
                },
            )

            if current:
                target_results[current.id] = {
                    "label": current.label,
                    "sql": target_sql,
                    "rows": rows,
                    "row_count": len(rows),
                    "status": "success",
                }

            next_idx = idx + 1
            base_update: dict = {
                "target_results": target_results,
                "database_results": rows,
                "sql_error": "",
                "usage": _merge_usage(
                    state, {"db_calls": 1, "db_success_calls": 1}
                ),
                "usage_steps": _merge_step_usage(
                    state, "database_executor", {"db_calls": 1, "db_success_calls": 1}
                ),
            }

            if next_idx < len(targets):
                return {
                    **base_update,
                    "current_target_index": next_idx,
                    "generated_sql": "",
                    "validation_error": "",
                    "validation_result": {},
                    "retry_count": 0,
                }

            return {
                **base_update,
                "current_target_index": next_idx,
            }

        except Exception as exc:
            log_event(
                "db_error",
                "database_executor",
                extra={"error": str(exc), "target_id": current.id if current else None},
            )
            if current:
                target_results[current.id] = {
                    "label": current.label,
                    "sql": target_sql,
                    "rows": [],
                    "row_count": 0,
                    "status": "failed",
                    "error": str(exc),
                }
            retries = state.get("retry_count", 0) + 1
            update = {
                "target_results": target_results,
                "sql_error": str(exc),
                "error_code": ErrorCode.DB_RUNTIME.value,
                "retry_count": retries,
                "usage": _merge_usage(
                    state, {"db_calls": 1, "db_failed_calls": 1}
                ),
                "usage_steps": _merge_step_usage(
                    state, "database_executor", {"db_calls": 1, "db_failed_calls": 1}
                ),
            }
            if retries > MAX_SQL_RETRIES_PER_TARGET:
                update["current_target_index"] = len(targets)
                update["pipeline_partial"] = True
            return update


def _analyze_rows_from_sql(state: AnalystState) -> dict | None:
    """Use SQL result rows directly — no LLM Python. Returns None to fall through."""
    rows = state.get("database_results") or []
    empty_insight = try_empty_rows_insight(state["user_query"], rows)
    if empty_insight:
        return {
            "python_code": "# No database rows — skip numeric extraction",
            "python_output": {"message": empty_insight, "no_rows": True},
            "final_insight": empty_insight,
        }

    sql = state.get("generated_sql", "")
    clarification = evaluate_disambiguation(
        state["user_query"],
        rows,
        sql,
        state.get("resolved_filters"),
    )
    if clarification:
        return {
            "python_code": "# Disambiguation required — multiple entity matches",
            "python_output": {
                "message": clarification.message,
                "disambiguation": True,
            },
            "needs_clarification": True,
            "clarification": clarification.model_dump(),
            "final_insight": clarification.message,
        }

    verified = extract_verified_facts(rows)
    output: dict = {"message": "SQL result rows — Python analysis skipped."}
    if verified:
        output["verified_facts"] = verified
    return {
        "python_code": "# Bypassed — facts extracted from database_results",
        "python_output": output,
    }


def python_analyzer_node(state: AnalystState) -> dict:
    with NodeTimer("python_analyzer"):
        query_mode = state.get("query_mode", "SINGLE")
        target_results = state.get("target_results") or {}

        if query_mode == "MULTI_STEP" and target_results:
            by_target = {}
            for tid, bundle in target_results.items():
                rows = bundle.get("rows") or []
                by_target[tid] = {
                    "label": bundle.get("label", tid),
                    "row_count": bundle.get("row_count", len(rows)),
                    "status": bundle.get("status", "success"),
                    "error": bundle.get("error"),
                    "rows": rows[:25],
                }
            return {
                "python_code": "# Multi-step — results aggregated per target",
                "python_output": {
                    "by_target": by_target,
                    "partial": bool(state.get("pipeline_partial")),
                },
            }

        if should_bypass_python_analyzer(
            state["user_query"],
            state.get("database_results") or [],
            sql=state.get("generated_sql", ""),
            query_mode=query_mode,
            execution_category=state.get("execution_category", ""),
        ):
            direct = _analyze_rows_from_sql(state)
            if direct is not None:
                return direct

        data_sample = state.get("database_results", [])[:2]
        instructional_payload = (
            f"User Analytical Goal: {state['user_query']}\n"
            f"Logical Calculation Plan: {state['logical_plan']}\n"
            f"Database Schema Sample: {data_sample}"
        )
        messages = [
            SystemMessage(content=PYTHON_ANALYZER_SYSTEM_PROMPT),
            HumanMessage(content=instructional_payload),
        ]
        response = llm_engine.invoke(messages)
        usage = _merge_usage(state, _llm_usage_delta(response))
        clean_script = response.content.strip().replace("```python", "").replace("```", "")

        sandbox_environment = {
            "dataset": state.get("database_results", []),
            "pd": pd,
            "result": {},
        }
        try:
            exec(clean_script, sandbox_environment)  # noqa: S102
            calculated = sandbox_environment.get("result", {})
            return {
                "python_code": clean_script,
                "python_output": calculated,
                "usage": usage,
                "usage_steps": _merge_step_usage(
                    state, "python_analyzer", _llm_usage_delta(response)
                ),
            }
        except Exception as exc:
            return {
                "python_code": clean_script,
                "python_output": {"error": str(exc)},
                "error_code": ErrorCode.PYTHON_SANDBOX.value,
                "usage": usage,
                "usage_steps": _merge_step_usage(
                    state, "python_analyzer", _llm_usage_delta(response)
                ),
            }


def insight_synthesizer_node(state: AnalystState) -> dict:
    with NodeTimer("insight_synthesizer"):
        if state.get("out_of_scope"):
            return {
                "final_insight": state.get("final_insight", OUT_OF_SCOPE_USER_MESSAGE)
            }

        if state.get("needs_clarification"):
            message = state.get("final_insight") or ""
            raw = state.get("clarification") or {}
            if isinstance(raw, dict) and raw.get("message"):
                message = raw["message"]
            return {"final_insight": message}

        rows = state.get("database_results") or []
        python_output = state.get("python_output", {})
        query_mode = state.get("query_mode", "SINGLE")
        target_results = state.get("target_results") or {}

        multi_insight = try_multi_target_insight(
            query_mode,
            state["user_query"],
            target_results,
            planned_targets=state.get("targets"),
        )
        if multi_insight:
            log_event("insight_grounded_multistep", "insight_synthesizer")
            return {"final_insight": multi_insight}

        empty_insight = try_empty_rows_insight(state["user_query"], rows)
        if empty_insight:
            log_event("insight_no_rows", "insight_synthesizer")
            return {"final_insight": empty_insight}

        deterministic = try_deterministic_insight(
            state["user_query"],
            rows,
            python_output if isinstance(python_output, dict) else None,
        )
        if deterministic:
            log_event(
                "insight_grounded",
                "insight_synthesizer",
                extra={"verified_facts": python_output.get("verified_facts", {})},
            )
            return {"final_insight": deterministic}

        if len(rows) > 1 and expects_single_entity_answer(state["user_query"]):
            blocked = try_blocked_ambiguous_entity_insight(
                state["user_query"], rows
            )
            if blocked:
                log_event("insight_blocked_ambiguous", "insight_synthesizer")
                return {"final_insight": blocked}

        clean_rows = sanitize_rows_for_insight(rows[:5])
        reporting_payload = (
            f"Original User Question: {state['user_query']}\n"
            f"Calculated Metrics: {python_output}\n"
            f"Verified Facts (use these numbers exactly): {python_output.get('verified_facts', {})}\n"
            f"Database Sample Rows: {clean_rows}"
        )
        messages = [
            SystemMessage(content=INSIGHT_SYNTHESIZER_SYSTEM_PROMPT),
            HumanMessage(content=reporting_payload),
        ]
        response = llm_engine.invoke(messages)
        return {
            "final_insight": sanitize_insight_text(response.content),
            "usage": _merge_usage(state, _llm_usage_delta(response)),
            "usage_steps": _merge_step_usage(
                state, "insight_synthesizer", _llm_usage_delta(response)
            ),
        }
