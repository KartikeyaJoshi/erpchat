"""Gate entity fuzzy-match extraction so it does not hijack employee / measure lookups."""

from __future__ import annotations

import re

from app.planning.attribute_lookup import is_attribute_lookup_query, is_inventory_stock_query
from app.schema.entity_metadata import tables_with_entity_metadata
from app.sql.entity_match_sql import EntityFilterSpec
from app.sql.target_templates import query_is_low_stock_threshold

# Fuzzy entity templates are for inventory / catalog / customer name matching only.
_ENTITY_MATCH_TABLES = frozenset(
    {"inventory", "products", "customers"},
)

_EMPLOYEE_DOMAIN_RE = re.compile(
    r"\b("
    r"salary|salaries|pay|payroll|compensation|payslip|payslips|"
    r"employee|employees|job\s+title|hire\s+date|department|departments"
    r")\b",
    re.IGNORECASE,
)

_CONDITION_PHRASE_RE = re.compile(
    r"\b("
    r"below|above|under|over|reorder|level|low\s+stock|currently|"
    r"which|what|out\s+of\s+stock"
    r")\b",
    re.IGNORECASE,
)


def _query_mentions_entity_measure(user_query: str) -> str | None:
    """Return table name when the query asks for a schema-defined entity measure."""
    q = user_query.lower()
    for table, entity in tables_with_entity_metadata().items():
        for measure in entity.measure_columns:
            m = measure.lower()
            if m in q or m.replace("_", " ") in q:
                return table
    return None


def _phrase_looks_like_condition(phrase: str) -> bool:
    """Reject entity phrases that are filter conditions, not record names."""
    text = phrase.strip()
    if not text:
        return True
    return bool(_CONDITION_PHRASE_RE.search(text))


def should_skip_entity_extractor(user_query: str) -> bool:
    """
    Skip strict_word_similarity entity extraction for queries that target
    employee/payroll measures, inventory thresholds, or attribute lookups —
    those should use templates or LLM SQL, not warehouse/product fuzzy templates.
    """
    text = user_query.strip()
    if not text:
        return False

    if _EMPLOYEE_DOMAIN_RE.search(text):
        return True

    if query_is_low_stock_threshold(text):
        return True

    measure_table = _query_mentions_entity_measure(text)
    if measure_table and measure_table not in _ENTITY_MATCH_TABLES:
        return True

    if is_attribute_lookup_query(text):
        return True

    return False


def is_entity_spec_allowed(user_query: str, spec: EntityFilterSpec) -> bool:
    """
    Reject an extracted entity spec when it conflicts with query intent
    (safety net if extraction still runs).
    """
    if should_skip_entity_extractor(user_query):
        return False

    if is_attribute_lookup_query(user_query) and not is_inventory_stock_query(user_query):
        return False

    if _phrase_looks_like_condition(spec.phrase):
        return False

    measure_table = _query_mentions_entity_measure(user_query)
    if measure_table and spec.table.lower() != measure_table.lower():
        return False

    if spec.table.lower() not in _ENTITY_MATCH_TABLES:
        return False

    return True
