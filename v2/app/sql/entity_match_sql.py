"""Build strict_word_similarity SQL from LLM-extracted entity specs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.config import ENTITY_MATCH_FAIR_MIN, SQL_ROW_LIMIT
from app.schema.loader import allowed_columns, allowed_tables

EntityQueryKind = Literal[
    "warehouse_stock",
    "sku_stock",
    "customer_lookup",
    "product_lookup",
]


@dataclass(frozen=True)
class EntityFilterSpec:
    query_kind: EntityQueryKind
    parameter: str
    table: str
    column: str
    phrase: str


def _escaped(text: str) -> str:
    return text.replace("'", "''")


def is_valid_spec(spec: EntityFilterSpec) -> bool:
    if spec.table not in allowed_tables():
        return False
    if spec.column not in allowed_columns(spec.table):
        return False
    if spec.parameter != spec.column:
        return False
    if not spec.phrase.strip():
        return False
    return True


def build_entity_match_sql(
    spec: EntityFilterSpec,
    *,
    resolved_filters: dict[str, str] | None = None,
) -> str:
    if not is_valid_spec(spec):
        raise ValueError("Invalid entity filter spec.")

    resolved_value = (resolved_filters or {}).get(spec.parameter)
    if resolved_value:
        return _build_exact_sql(spec, resolved_value)
    return _build_fuzzy_sql(spec)


def _build_exact_sql(spec: EntityFilterSpec, resolved_value: str) -> str:
    literal = _escaped(resolved_value.strip())
    if spec.query_kind == "warehouse_stock":
        return f"""SELECT
  i.warehouse_name AS warehouse_name,
  1.0 AS match_score,
  COALESCE(SUM(i.stock_on_hand), 0) AS total_stock_on_hand,
  COALESCE(SUM(i.stock_on_hand - i.allocated_stock), 0) AS total_available_stock
FROM inventory AS i
WHERE i.warehouse_name = '{literal}'
GROUP BY i.warehouse_name
ORDER BY match_score DESC
LIMIT {SQL_ROW_LIMIT}"""
    if spec.query_kind == "sku_stock":
        return f"""SELECT
  p.sku AS sku,
  1.0 AS match_score,
  i.warehouse_name AS warehouse_name,
  COALESCE(SUM(i.stock_on_hand), 0) AS stock_on_hand,
  COALESCE(SUM(i.stock_on_hand - i.allocated_stock), 0) AS available_stock
FROM products AS p
JOIN inventory AS i ON i.product_id = p.product_id
WHERE p.sku = '{literal}'
GROUP BY p.sku, i.warehouse_name
ORDER BY match_score DESC, i.warehouse_name
LIMIT {SQL_ROW_LIMIT}"""
    if spec.query_kind == "customer_lookup":
        return f"""SELECT
  c.company_name AS company_name,
  1.0 AS match_score,
  c.customer_id AS customer_id,
  c.credit_limit AS credit_limit,
  c.outstanding_balance AS outstanding_balance,
  c.city AS city,
  c.state AS state
FROM customers AS c
WHERE c.company_name = '{literal}'
ORDER BY match_score DESC, c.company_name
LIMIT {SQL_ROW_LIMIT}"""
    return f"""SELECT
  p.product_id AS product_id,
  p.product_name AS product_name,
  1.0 AS match_score,
  p.sku AS sku,
  p.category AS category,
  p.unit_price AS unit_price
FROM products AS p
WHERE p.product_name = '{literal}'
ORDER BY match_score DESC, p.product_name
LIMIT {SQL_ROW_LIMIT}"""


def _build_fuzzy_sql(spec: EntityFilterSpec) -> str:
    phrase = _escaped(spec.phrase.strip())
    if spec.query_kind == "warehouse_stock":
        return f"""SELECT
  i.warehouse_name AS warehouse_name,
  strict_word_similarity('{phrase}', i.warehouse_name) AS match_score,
  COALESCE(SUM(i.stock_on_hand), 0) AS total_stock_on_hand,
  COALESCE(SUM(i.stock_on_hand - i.allocated_stock), 0) AS total_available_stock
FROM inventory AS i
WHERE strict_word_similarity('{phrase}', i.warehouse_name) >= {ENTITY_MATCH_FAIR_MIN}
GROUP BY i.warehouse_name
ORDER BY match_score DESC
LIMIT {SQL_ROW_LIMIT}"""
    if spec.query_kind == "sku_stock":
        return f"""SELECT
  p.sku AS sku,
  strict_word_similarity('{phrase}', p.sku) AS match_score,
  i.warehouse_name AS warehouse_name,
  COALESCE(SUM(i.stock_on_hand), 0) AS stock_on_hand,
  COALESCE(SUM(i.stock_on_hand - i.allocated_stock), 0) AS available_stock
FROM products AS p
JOIN inventory AS i ON i.product_id = p.product_id
WHERE strict_word_similarity('{phrase}', p.sku) >= {ENTITY_MATCH_FAIR_MIN}
GROUP BY p.sku, i.warehouse_name
ORDER BY match_score DESC, i.warehouse_name
LIMIT {SQL_ROW_LIMIT}"""
    if spec.query_kind == "customer_lookup":
        return f"""SELECT
  c.company_name AS company_name,
  strict_word_similarity('{phrase}', c.company_name) AS match_score,
  c.customer_id AS customer_id,
  c.credit_limit AS credit_limit,
  c.outstanding_balance AS outstanding_balance,
  c.city AS city,
  c.state AS state
FROM customers AS c
WHERE strict_word_similarity('{phrase}', c.company_name) >= {ENTITY_MATCH_FAIR_MIN}
ORDER BY match_score DESC, c.company_name
LIMIT {SQL_ROW_LIMIT}"""
    return f"""SELECT
  p.product_id AS product_id,
  p.product_name AS product_name,
  strict_word_similarity('{phrase}', p.product_name) AS match_score,
  p.sku AS sku,
  p.category AS category,
  p.unit_price AS unit_price
FROM products AS p
WHERE strict_word_similarity('{phrase}', p.product_name) >= {ENTITY_MATCH_FAIR_MIN}
ORDER BY match_score DESC, p.product_name
LIMIT {SQL_ROW_LIMIT}"""
