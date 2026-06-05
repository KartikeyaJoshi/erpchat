"""Schema-driven column filter strategies: exact vs fuzzy matching."""

from __future__ import annotations

import re
from typing import Literal

from app.schema.loader import load_schema, table_primary_key

FilterKind = Literal[
    "exact_numeric",
    "exact_code",
    "exact_text",
    "fuzzy_text",
    "exact_enum",
]

_NUMERIC_ID_RE = re.compile(r"_id$")
_DATE_LIKE_RE = re.compile(r"(_date|_timestamp|^created_at$|^updated_at$)")


def _table_meta(table: str) -> dict:
    return load_schema().get("tables", {}).get(table, {})


def column_filter_overrides(table: str) -> dict[str, str]:
    meta = _table_meta(table)
    return dict(meta.get("column_filters") or {})


def column_filter_kind(table: str, column: str) -> FilterKind:
    """
    Decide how to filter a column from natural-language input.

    Inferred from schema roles (PK, FK, enums, entity lookup/label columns) with
    optional per-table overrides in erp_schema.json ``column_filters``.
    """
    overrides = column_filter_overrides(table)
    if column in overrides:
        return overrides[column]  # type: ignore[return-value]

    meta = _table_meta(table)
    col_l = column.lower()
    pk = (meta.get("primary_key") or table_primary_key(table) or "").lower()
    enums = meta.get("enums") or {}
    entity = meta.get("entity") or {}
    foreign_keys = meta.get("foreign_keys") or {}

    if col_l in {k.lower() for k in enums}:
        return "exact_enum"

    if col_l in ("sku",) or col_l.endswith("_code"):
        return "exact_code"

    if col_l == "email":
        return "exact_text"

    if col_l.startswith("is_"):
        return "exact_numeric"

    measures = {c.lower() for c in entity.get("measure_columns") or ()}
    if col_l in measures:
        return "exact_numeric"

    if _NUMERIC_ID_RE.search(col_l):
        if col_l == pk or col_l in {k.lower() for k in foreign_keys}:
            return "exact_numeric"
        return "exact_numeric"

    if _DATE_LIKE_RE.search(col_l):
        return "exact_text"

    lookups = {c.lower() for c in entity.get("lookup_columns") or ()}
    labels = {c.lower() for c in entity.get("label_columns") or ()}

    if col_l in lookups or col_l in labels:
        if col_l.endswith("_name") or col_l in (
            "first_name",
            "last_name",
            "contact_name",
            "movement_type",
        ):
            return "fuzzy_text"
        if _NUMERIC_ID_RE.search(col_l):
            return "exact_numeric"
        if col_l.endswith("_code"):
            return "exact_code"
        return "fuzzy_text"

    if col_l.endswith("_name"):
        return "fuzzy_text"

    return "exact_text"


def allows_fuzzy_match(table: str, column: str) -> bool:
    return column_filter_kind(table, column) == "fuzzy_text"


def fuzzy_text_columns(table: str) -> tuple[str, ...]:
    meta = _table_meta(table)
    entity = meta.get("entity") or {}
    cols: list[str] = []
    seen: set[str] = set()
    for key in ("lookup_columns", "label_columns"):
        for col in entity.get(key) or ():
            if col not in seen and allows_fuzzy_match(table, col):
                cols.append(col)
                seen.add(col)
    return tuple(cols)


def format_filter_rules_for_prompt() -> str:
    """Short rules block for SQL / entity prompts."""
    lines = [
        "Column filter rules (use for WHERE clauses):",
        "- Numeric PK/FK columns (*_id, payslip_id, etc.): exact equality with parsed integer — NEVER strict_word_similarity.",
        "- SKU and *_code columns: exact string match.",
        "- Text name columns (product_name, company_name, warehouse_name, first_name, etc.): strict_word_similarity when the user gives a name fragment.",
        "- Enum columns: exact match on allowed enum value.",
        "- Example: 'status of Order 408' → WHERE order_id = 408 (not similarity on order_id).",
    ]
    return "\n".join(lines)
