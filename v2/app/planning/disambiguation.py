"""Schema-driven disambiguation for ambiguous single-entity lookups."""

from __future__ import annotations

import re
from typing import Any

from app.config import SQL_ROW_LIMIT
from app.contracts.clarification import ClarificationOption, ClarificationPayload
from app.planning.attribute_lookup import (
    extract_entity_phrase,
    expects_single_entity_answer,
    parse_attribute_lookup_intent,
    requested_attribute_column,
    sql_uses_fuzzy_entity_match,
)
from app.planning.sql_shape import (
    analyze_sql_shape,
    is_ambiguous_single_entity_lookup,
    shape_filters_primary_key,
)
from app.schema.entity_metadata import (
    EntityMetadata,
    get_entity_metadata,
    resolve_table_from_filter_key,
)

_AGGREGATE_RE = re.compile(
    r"\b(total|sum|average|avg|mean|count|how\s+many|number\s+of|all)\b",
    re.IGNORECASE,
)
_LISTING_RE = re.compile(
    r"\b(list|show\s+all|every|each|top\s+\d+|rank|ranked|breakdown|by\s+\w+)\b",
    re.IGNORECASE,
)
_RANKING_RE = re.compile(
    r"\b(top|bottom|highest|lowest|best|worst|leading)\b",
    re.IGNORECASE,
)


def is_intentional_multi_row_query(user_query: str) -> bool:
    """Skip disambiguation when the user clearly asked for many rows or aggregates."""
    text = user_query.strip()
    if not text:
        return True
    if _AGGREGATE_RE.search(text):
        return True
    if _LISTING_RE.search(text):
        return True
    if _RANKING_RE.search(text):
        return True
    return False


def _escaped(value: str) -> str:
    return value.replace("'", "''")


def _fix_disambiguation_sql(
    sql: str,
    entity: EntityMetadata,
    *,
    attribute_column: str | None = None,
) -> str | None:
    pk = entity.primary_key
    select_cols = list(dict.fromkeys([pk, *entity.label_columns]))
    if attribute_column and attribute_column not in select_cols:
        select_cols.append(attribute_column)
    where_match = re.search(r"\bwhere\b", sql, re.IGNORECASE)
    if not where_match:
        return None
    tail = sql[where_match.start() :].strip().rstrip(";")
    cols_sql = ", ".join(select_cols)
    return f"SELECT {cols_sql} FROM public.{entity.table} {tail}"


def fetch_entity_rows_for_disambiguation(
    sql: str,
    entity: EntityMetadata,
    *,
    attribute_column: str | None = None,
) -> list[dict[str, Any]]:
    disc_sql = _fix_disambiguation_sql(
        sql, entity, attribute_column=attribute_column
    )
    if not disc_sql:
        return []
    from app.database import supabase_client

    try:
        response = supabase_client.rpc(
            "execute_raw_sql",
            {"query_text": disc_sql},
        ).execute()
        return list(response.data or [])
    except Exception:
        return []


def _row_value(row: dict[str, Any], *names: str) -> Any:
    lower_map = {str(k).lower(): v for k, v in row.items()}
    for name in names:
        val = lower_map.get(name.lower())
        if val is not None and str(val).strip() != "":
            return val
    return None


def _rows_have_primary_key(entity: EntityMetadata, rows: list[dict[str, Any]]) -> bool:
    if not rows:
        return False
    pk = entity.primary_key
    return any(
        pk in row or pk.lower() in {str(k).lower() for k in row}
        for row in rows
    )


def _dedupe_by_pk(entity: EntityMetadata, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    pk = entity.primary_key
    seen: set[Any] = set()
    unique: list[dict[str, Any]] = []
    for row in rows:
        key = _row_value(row, pk)
        if key is None:
            unique.append(row)
            continue
        if key in seen:
            continue
        seen.add(key)
        unique.append(row)
    return unique


def _primary_key_value(entity: EntityMetadata, row: dict[str, Any]) -> str:
    pk_val = _row_value(row, entity.primary_key)
    return str(pk_val) if pk_val is not None else ""


def _build_natural_label(entity: EntityMetadata, row: dict[str, Any]) -> str:
    """User-facing option text from schema label_columns — no column names exposed."""
    cols = [c.lower() for c in entity.label_columns]
    values = {c.lower(): _row_value(row, c) for c in entity.label_columns}

    if "first_name" in cols and "last_name" in cols:
        first = values.get("first_name") or ""
        last = values.get("last_name") or ""
        name = f"{first} {last}".strip() or "Unknown person"
        extras = [
            str(values[c])
            for c in cols
            if c not in {"first_name", "last_name"} and values.get(c)
        ]
        return f"{name} — {extras[0]}" if len(extras) == 1 else (
            f"{name} — {', '.join(extras)}" if extras else name
        )

    if "company_name" in cols and "contact_name" in cols:
        company = values.get("company_name")
        contact = values.get("contact_name")
        city = values.get("city")
        if company and contact:
            base = f"{company} ({contact})"
        else:
            base = str(company or contact or "Unknown customer")
        return f"{base}, {city}" if city else base

    if "product_name" in cols:
        name = values.get("product_name") or "Unknown product"
        category = values.get("category")
        return f"{name} ({category})" if category else str(name)

    if "warehouse_name" in cols and len(cols) == 1:
        wh = values.get("warehouse_name")
        return f"Stock at {wh}" if wh else "Warehouse stock record"

    if "dept_name" in cols:
        return str(values.get("dept_name") or "Unknown department")

    if "account_name" in cols:
        name = values.get("account_name") or "Unknown account"
        atype = values.get("account_type")
        return f"{name} ({atype})" if atype else str(name)

    if "period_start" in cols and "period_end" in cols:
        start = values.get("period_start")
        end = values.get("period_end")
        if start and end:
            return f"Payslip {start} to {end}"
        return str(start or end or "Payslip record")

    parts = [str(values[c]) for c in cols if values.get(c)]
    if parts:
        return " — ".join(parts)

    for key in ("name", "title", "label", "description"):
        val = _row_value(row, key)
        if val:
            return str(val)
    return "Matching record"


def _build_clarification_message(
    entity_noun: str,
    phrase: str,
    options: list[ClarificationOption],
) -> str:
    entity_plural = (
        f"{entity_noun}s" if not entity_noun.endswith("s") else entity_noun
    )
    lines = [
        f"Several {entity_plural} match “{phrase}”.",
        "Please select the one you mean:",
    ]
    for index, option in enumerate(options, start=1):
        lines.append(f"{index}. {option.label}")
    lines.append(
        "If none of these are correct, provide a unique detail that identifies "
        "the right record (for example job title or work email)."
    )
    return "\n".join(lines)


def _build_option_label(
    entity: EntityMetadata, row: dict[str, Any]
) -> tuple[str, str]:
    canonical = _primary_key_value(entity, row)
    label = _build_natural_label(entity, row)
    return canonical, label


def _should_skip_disambiguation(
    user_query: str,
    rows: list[dict[str, Any]],
) -> bool:
    """
    Skip warehouse-style disambiguation when the user asked for a product-level
    attribute (e.g. category by exact SKU) — one value per product, not per warehouse.
    """
    intent = parse_attribute_lookup_intent(user_query)
    if intent is None:
        return False

    if intent.is_boolean:
        return False

    if intent.table == "products" and intent.filter_column.lower() == "sku":
        return True

    if intent.attribute_column and rows:
        values: set[str] = set()
        for row in rows:
            val = _row_value(row, intent.attribute_column)
            if val is not None and str(val).strip() != "":
                values.add(str(val).strip())
        if len(values) == 1:
            return True

    return False


def evaluate_disambiguation(
    user_query: str,
    rows: list[dict[str, Any]],
    sql: str,
    resolved_filters: dict[str, str] | None,
) -> ClarificationPayload | None:
    """
    If SQL shape + schema roles indicate a single-entity lookup but multiple rows
    matched, return a clarification payload with PK-backed options.
    """
    if not rows or len(rows) <= 1:
        return None

    if is_intentional_multi_row_query(user_query):
        return None

    if _should_skip_disambiguation(user_query, rows):
        return None

    resolved = dict(resolved_filters or {})
    for key in resolved:
        if resolve_table_from_filter_key(key):
            return None

    shape = analyze_sql_shape(sql or "")
    if shape is None or not shape.primary_table:
        return None

    entity = get_entity_metadata(shape.primary_table)
    if entity is None:
        return None

    if shape_filters_primary_key(shape, entity):
        return None

    attr_col = requested_attribute_column(user_query)
    ambiguous = is_ambiguous_single_entity_lookup(shape, entity, rows)
    if not ambiguous and expects_single_entity_answer(user_query):
        if sql_uses_fuzzy_entity_match(sql) and len(rows) > 1:
            ambiguous = True
        elif any(
            "match_score" in {str(k).lower() for k in row}
            for row in rows
            if isinstance(row, dict)
        ) and len(rows) > 1:
            ambiguous = True

    if not ambiguous:
        return None

    phrase = extract_entity_phrase(user_query)

    candidate_rows = list(rows)
    if not _rows_have_primary_key(entity, candidate_rows):
        enriched = fetch_entity_rows_for_disambiguation(
            sql, entity, attribute_column=attr_col
        )
        if enriched:
            candidate_rows = enriched

    candidate_rows = _dedupe_by_pk(entity, candidate_rows)
    if len(candidate_rows) <= 1:
        return None

    options: list[ClarificationOption] = []
    for row in candidate_rows[:10]:
        value, label = _build_option_label(entity, row)
        if not value:
            continue
        options.append(ClarificationOption(value=value, label=label, score=1.0))

    if len(options) <= 1:
        return None

    message = _build_clarification_message(entity.noun, phrase, options)
    return ClarificationPayload(
        parameter=entity.primary_key,
        original_phrase=phrase,
        options=options,
        message=message,
    )


def _extract_select_clause(sql: str) -> str | None:
    match = re.search(
        r"select\s+(distinct\s+)?(.+?)\s+from\b",
        sql,
        re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return None
    return match.group(2).strip()


def build_resolved_entity_sql(
    user_query: str,
    resolved_filters: dict[str, str],
    original_sql: str | None = None,
) -> str | None:
    """Exact SQL when the client supplies a PK from a prior clarification."""
    resolved = dict(resolved_filters or {})
    if not resolved:
        return None

    for filter_key, filter_value in resolved.items():
        entity = resolve_table_from_filter_key(filter_key)
        if entity is None:
            continue

        pk = entity.primary_key
        literal = _escaped(str(filter_value).strip())

        if original_sql:
            select_clause = _extract_select_clause(original_sql)
            if select_clause:
                return (
                    f"SELECT {select_clause} FROM public.{entity.table} "
                    f"WHERE {pk} = '{literal}' LIMIT {SQL_ROW_LIMIT}"
                )

        if entity.measure_columns:
            cols = ", ".join(entity.measure_columns[:3])
            return (
                f"SELECT {cols} FROM public.{entity.table} "
                f"WHERE {pk} = '{literal}' LIMIT {SQL_ROW_LIMIT}"
            )

        label_cols = ", ".join(
            list(dict.fromkeys([pk, *entity.label_columns]))[:6]
        )
        return (
            f"SELECT {label_cols} FROM public.{entity.table} "
            f"WHERE {pk} = '{literal}' LIMIT {SQL_ROW_LIMIT}"
        )

    return None


def clarification_from_state(state: dict[str, Any]) -> ClarificationPayload | None:
    raw = state.get("clarification")
    if not raw:
        return None
    if isinstance(raw, ClarificationPayload):
        return raw
    return ClarificationPayload.model_validate(raw)
