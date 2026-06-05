"""Load governed ERP schema for prompts and validation."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

_SCHEMA_PATH = Path(__file__).parent / "erp_schema.json"


@lru_cache(maxsize=1)
def load_schema() -> dict:
    with _SCHEMA_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def allowed_tables() -> set[str]:
    return set(load_schema()["tables"].keys())


def allowed_columns(table: str) -> set[str]:
    tables = load_schema()["tables"]
    if table not in tables:
        return set()
    return set(tables[table]["columns"])


def all_allowed_columns() -> dict[str, set[str]]:
    return {t: allowed_columns(t) for t in allowed_tables()}


def table_primary_key(table: str) -> str | None:
    schema = load_schema()
    meta = schema.get("tables", {}).get(table, {})
    return meta.get("primary_key")


def format_schema_for_prompt() -> str:
    """Human-readable schema block for LLM prompts."""
    schema = load_schema()
    lines = ["Target Schema Tables & Column Mappings:"]
    for idx, (table, meta) in enumerate(schema["tables"].items(), start=1):
        cols = ", ".join(meta["columns"])
        lines.append(f"{idx}. public.{table}")
        lines.append(f"   - Columns: {cols}")
        if meta.get("enums"):
            for col, values in meta["enums"].items():
                lines.append(f"   - {col} allowed values: {', '.join(values)}")
    lines.append("")
    from app.schema.column_filter import format_filter_rules_for_prompt

    lines.append(format_filter_rules_for_prompt())
    return "\n".join(lines)


def format_metric_definitions() -> str:
    schema = load_schema()
    metrics = schema.get("metric_definitions", {})
    if not metrics:
        return ""
    lines = ["Business metric definitions:"]
    for key, value in metrics.items():
        lines.append(f"- {key}: {value}")
    return "\n".join(lines)


ERP_SCHEMA_CONTEXT = format_schema_for_prompt()
METRIC_DEFINITIONS_CONTEXT = format_metric_definitions()
