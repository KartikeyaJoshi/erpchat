"""LLM-based entity phrase extraction for hybrid LLM + DB scoring."""

from __future__ import annotations

import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.contracts.entity_extraction import EntityExtractionOutput
from app.observability.logging import log_event
from app.prompts import ENTITY_FILTER_EXTRACTOR_SYSTEM_PROMPT
from app.sql.entity_match_sql import EntityFilterSpec


def _strip_json_markdown(text: str) -> str:
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned.strip()


def _extract_json_object(text: str) -> str:
    match = re.search(r"\{[\s\S]*\}", text)
    return match.group(0).strip() if match else text.strip()


def _parse_payload(raw_text: str) -> EntityExtractionOutput | None:
    raw = _strip_json_markdown(raw_text)
    candidates = [raw, _extract_json_object(raw)]
    for candidate in candidates:
        try:
            return EntityExtractionOutput.model_validate_json(candidate)
        except Exception:  # noqa: BLE001
            continue
    return None


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


def extract_entity_filter(
    *,
    llm: Any,
    user_query: str,
    schema_context: str,
    metric_definitions: str,
) -> tuple[EntityFilterSpec | None, dict[str, int]]:
    usage = {"llm_prompt_tokens": 0, "llm_completion_tokens": 0, "llm_total_tokens": 0}
    messages = [
        SystemMessage(
            content=ENTITY_FILTER_EXTRACTOR_SYSTEM_PROMPT.format(
                schema_context=schema_context,
                metric_definitions=metric_definitions,
            )
        ),
        HumanMessage(content=user_query),
    ]
    response = llm.invoke(messages)
    first_usage = _llm_usage_delta(response)
    usage = {k: usage.get(k, 0) + first_usage.get(k, 0) for k in usage}
    raw = str(response.content)
    payload = _parse_payload(raw)
    if payload is None:
        repair_messages = [
            SystemMessage(
                content=(
                    "Convert the following content into VALID JSON only. "
                    "Do not add prose, code fences, or explanations. "
                    "Required keys: use_entity_match, query_kind, parameter, table, column, phrase."
                )
            ),
            HumanMessage(content=raw),
        ]
        repaired = llm.invoke(repair_messages)
        repair_usage = _llm_usage_delta(repaired)
        usage = {k: usage.get(k, 0) + repair_usage.get(k, 0) for k in usage}
        repaired_raw = str(repaired.content)
        payload = _parse_payload(repaired_raw)
    if payload is None:
        log_event("entity_extract_parse_failed", "entity_extractor")
        return None, usage

    if not payload.use_entity_match or payload.query_kind == "none":
        return None, usage
    if not payload.phrase.strip() or not payload.column.strip() or not payload.table.strip():
        return None, usage

    return (
        EntityFilterSpec(
            query_kind=payload.query_kind,  # type: ignore[arg-type]
            parameter=payload.parameter or payload.column,
            table=payload.table,
            column=payload.column,
            phrase=payload.phrase.strip(),
        ),
        usage,
    )
