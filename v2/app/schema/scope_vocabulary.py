"""Schema-derived vocabulary for in-scope query detection."""

from __future__ import annotations

import re
from functools import lru_cache

from app.schema.loader import load_schema

# Human synonyms for governed column names used in natural-language questions.
_COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "unit_price": ("price", "pricing"),
    "cost_price": ("cost",),
    "product_name": ("product",),
    "company_name": ("company",),
    "contact_name": ("contact",),
    "credit_limit": ("credit",),
    "outstanding_balance": ("outstanding",),
    "stock_on_hand": ("stock",),
    "warehouse_name": ("warehouse",),
    "dept_name": ("department",),
    "account_name": ("account",),
    "gross_salary": ("gross",),
    "net_salary": ("net",),
}

_SKU_CODE_RE = re.compile(r"\bsku[-\w\d]+", re.IGNORECASE)

_ENTITY_LOOKUP_RE = re.compile(
    r"^\s*what\s+is\s+the\s+(\w+(?:\s+\w+)?)\s+(?:for|of)\s+",
    re.IGNORECASE,
)

_STOP_TERMS = frozenset(
    {
        "and",
        "for",
        "the",
        "from",
        "with",
        "date",
        "type",
        "name",
        "code",
        "limit",
    }
)


@lru_cache(maxsize=1)
def scope_vocabulary() -> frozenset[str]:
    """Terms derived from erp_schema columns, entity metadata, and aliases."""
    terms: set[str] = set()
    schema = load_schema()
    for table_meta in schema.get("tables", {}).values():
        columns = list(table_meta.get("columns") or [])
        entity = table_meta.get("entity") or {}
        for key in ("label_columns", "lookup_columns", "measure_columns"):
            columns.extend(entity.get(key) or [])

        for col in columns:
            col_l = str(col).lower().strip()
            if not col_l:
                continue
            terms.add(col_l)
            terms.add(col_l.replace("_", " "))
            for alias in _COLUMN_ALIASES.get(col_l, ()):
                terms.add(alias.lower())

    return frozenset(t for t in terms if len(t) >= 3 and t not in _STOP_TERMS)


def _term_in_query(query: str, term: str) -> bool:
    if " " in term:
        return term in query
    return re.search(rf"\b{re.escape(term)}\b", query, re.IGNORECASE) is not None


def query_matches_scope_vocabulary(query: str) -> bool:
    q = query.lower()
    for term in scope_vocabulary():
        if _term_in_query(q, term):
            return True
    return False


def query_has_sku_reference(query: str) -> bool:
    return bool(_SKU_CODE_RE.search(query))


def looks_like_entity_record_lookup(query: str) -> bool:
    """
    True for ERP record attribute questions such as
    'What is the price for Product X?' or 'What is the category of SKU-…?'
    """
    text = query.strip()
    if not text:
        return False

    if query_has_sku_reference(text):
        return True

    match = _ENTITY_LOOKUP_RE.match(text)
    if match:
        attribute = match.group(1).lower().strip()
        if attribute.replace(" ", "_") in scope_vocabulary() or attribute in scope_vocabulary():
            return True
        for term in scope_vocabulary():
            if term in attribute or attribute in term:
                return True

    if re.search(r"\b(for|of)\s+[\w\d]", text, re.IGNORECASE):
        return query_matches_scope_vocabulary(text)

    return False
