"""Schema-driven attribute lookup: requested column + entity key → exact SQL."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from app.config import SQL_ROW_LIMIT
from app.planning.record_reference import resolve_record_filter
from app.schema.entity_metadata import EntityMetadata, get_entity_metadata
from app.schema.loader import allowed_columns, load_schema
from app.schema.scope_vocabulary import _COLUMN_ALIASES

MatchMode = Literal["exact", "similarity"]

_SKU_CODE_RE = re.compile(r"\b(sku[-\w\d]+)\b", re.IGNORECASE)

_ATTRIBUTE_PHRASE_RE = re.compile(
    r"\bwhat\s+is\s+the\s+(\w+(?:\s+\w+)?)\s+(?:for|of)\b",
    re.IGNORECASE,
)

_IS_BOOLEAN_RE = re.compile(
    r"^\s*is\s+(.+?)\s+(discontinued|active|inactive)\s*\??\s*$",
    re.IGNORECASE,
)

# Natural-language status words → (table, column)
_BOOLEAN_STATUS_MAP: dict[str, tuple[str, str]] = {
    "discontinued": ("products", "is_discontinued"),
    "active": ("customers", "is_active"),
    "inactive": ("customers", "is_active"),
}

_STOCK_INVENTORY_INTENT_RE = re.compile(
    r"\b("
    r"stock|inventory|warehouse|warehouses|available\s+stock|on\s+hand|"
    r"reorder|allocated|low\s+stock|in\s+stock"
    r")\b",
    re.IGNORECASE,
)

_SINGLE_ENTITY_QUESTION_RE = re.compile(
    r"^\s*(?:what\s+is\s+the|is\s+|does\s+|has\s+|can\s+)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class AttributeLookupIntent:
    table: str
    attribute_column: str
    filter_column: str
    filter_value: str
    match_mode: MatchMode
    entity_phrase: str
    is_boolean: bool = False
    filter_value_is_numeric: bool = False


def _escaped(value: str) -> str:
    return value.replace("'", "''")


def extract_sku_code(query: str) -> str | None:
    match = _SKU_CODE_RE.search(query)
    if not match:
        return None
    return match.group(1).strip()


def extract_entity_phrase(query: str) -> str:
    boolean_match = _IS_BOOLEAN_RE.match(query.strip())
    if boolean_match:
        return boolean_match.group(1).strip()

    match = re.search(
        r"\b(?:for|of)\s+['\"]?(.+?)['\"]?\s*[?.!]?\s*$",
        query,
        re.IGNORECASE,
    )
    if match:
        return match.group(1).strip()
    return query.strip().rstrip("?.")


def is_inventory_stock_query(query: str) -> bool:
    return bool(_STOCK_INVENTORY_INTENT_RE.search(query))


def expects_single_entity_answer(query: str) -> bool:
    """True when the user expects one record's attribute, not a listing."""
    text = query.strip()
    if not text:
        return False
    if is_intentional_list_query(text):
        return False
    if parse_attribute_lookup_intent(text) is not None:
        return True
    if _IS_BOOLEAN_RE.match(text):
        return True
    if _ATTRIBUTE_PHRASE_RE.search(text):
        return True
    if _SINGLE_ENTITY_QUESTION_RE.match(text) and not is_inventory_stock_query(text):
        return True
    return False


def is_intentional_list_query(query: str) -> bool:
    return bool(
        re.search(
            r"\b(list|show\s+all|every|each|all\s+products|all\s+customers)\b",
            query,
            re.IGNORECASE,
        )
    )


def resolve_boolean_attribute(query: str) -> tuple[str, str] | None:
    match = _IS_BOOLEAN_RE.match(query.strip())
    if not match:
        return None
    status_word = match.group(2).lower().strip()
    mapping = _BOOLEAN_STATUS_MAP.get(status_word)
    if not mapping:
        return None
    table, column = mapping
    if column not in allowed_columns(table):
        return None
    return table, column


def _resolve_attribute_on_table(
    phrase: str,
    table: str,
    columns: list[str],
) -> str | None:
    phrase_key = phrase.lower().strip().replace(" ", "_")
    col_map = {c.lower(): c for c in columns}
    if phrase_key in col_map:
        return col_map[phrase_key]
    for col in columns:
        col_l = col.lower()
        if phrase_key == col_l or phrase.replace("_", " ") == col_l.replace("_", " "):
            return col
        for alias in _COLUMN_ALIASES.get(col_l, ()):
            if phrase.lower() == alias or phrase_key == alias.replace(" ", "_"):
                return col
    return None


def resolve_requested_attribute(query: str) -> tuple[str, str] | None:
    """Map natural-language attribute phrase to (table, column)."""
    boolean = resolve_boolean_attribute(query)
    if boolean:
        return boolean

    match = _ATTRIBUTE_PHRASE_RE.search(query)
    if not match:
        return None

    phrase = match.group(1).lower().strip()
    schema = load_schema()
    for table, meta in schema.get("tables", {}).items():
        columns = list(meta.get("columns") or [])
        entity = meta.get("entity") or {}
        for key in ("label_columns", "measure_columns", "lookup_columns"):
            for col in entity.get(key) or []:
                if col not in columns:
                    columns.append(col)

        resolved = _resolve_attribute_on_table(phrase, table, columns)
        if resolved:
            return table, resolved

    return None


def _pick_filter_for_table(
    table: str,
    query: str,
    entity: EntityMetadata | None,
) -> tuple[str, str, MatchMode, bool] | None:
    record = resolve_record_filter(
        table,
        phrase=extract_entity_phrase(query),
        sku=extract_sku_code(query),
        entity=entity,
    )
    if record is None:
        return None
    return record.column, record.value, record.match_mode, record.value_is_numeric


def parse_attribute_lookup_intent(user_query: str) -> AttributeLookupIntent | None:
    text = user_query.strip()
    if not text or is_inventory_stock_query(text):
        return None

    resolved = resolve_requested_attribute(text)
    if not resolved:
        return None

    table, attribute_column = resolved
    entity = get_entity_metadata(table)
    if entity is None and table not in load_schema().get("tables", {}):
        return None
    if attribute_column not in allowed_columns(table):
        return None

    filter_spec = _pick_filter_for_table(table, text, entity)
    if not filter_spec:
        return None

    filter_column, filter_value, match_mode, value_is_numeric = filter_spec
    if not filter_value.strip():
        return None

    if table == "products" and filter_column.lower() == "sku":
        match_mode = "exact"

    is_boolean = resolve_boolean_attribute(text) is not None

    return AttributeLookupIntent(
        table=table,
        attribute_column=attribute_column,
        filter_column=filter_column,
        filter_value=filter_value.strip(),
        match_mode=match_mode,
        entity_phrase=extract_entity_phrase(text),
        is_boolean=is_boolean,
        filter_value_is_numeric=value_is_numeric,
    )


def is_attribute_lookup_query(user_query: str) -> bool:
    return parse_attribute_lookup_intent(user_query) is not None


def _select_columns_for_intent(intent: AttributeLookupIntent) -> list[str]:
    entity = get_entity_metadata(intent.table)
    pk = entity.primary_key if entity else None
    parts: list[str] = []
    if pk:
        parts.append(pk)
    if entity:
        for col in entity.label_columns:
            if col != intent.attribute_column and col not in parts:
                parts.append(col)
    if intent.attribute_column not in parts:
        parts.append(intent.attribute_column)
    return parts


def _where_predicate(intent: AttributeLookupIntent) -> str:
    col = intent.filter_column
    if intent.match_mode == "similarity":
        literal = _escaped(intent.filter_value)
        return (
            f"strict_word_similarity('{literal}', {col}) >= 0.4"
        )
    if intent.filter_value_is_numeric:
        return f"{col} = {intent.filter_value}"
    literal = _escaped(intent.filter_value)
    return f"{col} = '{literal}'"


def build_attribute_lookup_sql(
    intent: AttributeLookupIntent,
    *,
    resolved_filters: dict[str, str] | None = None,
) -> str:
    resolved = dict(resolved_filters or {})
    entity = get_entity_metadata(intent.table)

    if entity and entity.primary_key in resolved:
        pk_val = resolved[entity.primary_key]
        col = intent.attribute_column
        if pk_val.isdigit():
            where = f"{entity.primary_key} = {pk_val}"
        else:
            where = f"{entity.primary_key} = '{_escaped(pk_val)}'"
        return (
            f"SELECT {col} FROM public.{intent.table} "
            f"WHERE {where} LIMIT {SQL_ROW_LIMIT}"
        )

    select_cols = ", ".join(_select_columns_for_intent(intent))
    table = intent.table
    where = _where_predicate(intent)

    if intent.match_mode == "exact":
        return (
            f"SELECT {select_cols} FROM public.{table} "
            f"WHERE {where} LIMIT {SQL_ROW_LIMIT}"
        )

    literal = _escaped(intent.filter_value)
    return (
        f"SELECT {select_cols}, "
        f"strict_word_similarity('{literal}', {intent.filter_column}) AS match_score "
        f"FROM public.{table} "
        f"WHERE {where} "
        f"ORDER BY match_score DESC LIMIT {SQL_ROW_LIMIT}"
    )


def try_attribute_lookup_sql(
    user_query: str,
    resolved_filters: dict[str, str] | None = None,
) -> str | None:
    intent = parse_attribute_lookup_intent(user_query)
    if intent is None:
        return None
    return build_attribute_lookup_sql(intent, resolved_filters=resolved_filters)


def requested_attribute_column(user_query: str) -> str | None:
    resolved = resolve_requested_attribute(user_query)
    return resolved[1] if resolved else None


def attribute_lookup_grain_table(user_query: str) -> str | None:
    intent = parse_attribute_lookup_intent(user_query)
    return intent.table if intent else None


def sql_uses_fuzzy_entity_match(sql: str) -> bool:
    text = (sql or "").lower()
    return "strict_word_similarity" in text or "match_score" in text
