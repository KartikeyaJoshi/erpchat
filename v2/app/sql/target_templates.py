"""Deterministic SQL templates for well-known multi-step targets."""

from __future__ import annotations

import re

from app.config import SQL_ROW_LIMIT
from app.contracts.targets import QueryTarget
from app.planning.decomposition import parse_credit_threshold, parse_rank_limit, parse_sku
from app.planning.extremum_lookup import try_extremum_template_sql


def _fast_movers_low_stock_sql(year: int, row_limit: int) -> str:
    """Top 3 products by units sold with stock at every warehouse (includes is_low flag)."""
    next_year = year + 1
    return f"""WITH fast_movers AS (
  SELECT oi.product_id, SUM(oi.quantity) AS units_sold
  FROM order_items oi
  INNER JOIN sales_orders so ON so.order_id = oi.order_id
  WHERE so.order_date >= '{year}-01-01' AND so.order_date < '{next_year}-01-01'
    AND so.status NOT IN ('Draft', 'Cancelled')
  GROUP BY oi.product_id
  ORDER BY units_sold DESC
  LIMIT 3
)
SELECT
  p.product_id,
  p.sku,
  p.product_name,
  fm.units_sold,
  i.warehouse_name,
  i.stock_on_hand - i.allocated_stock AS available_stock,
  i.reorder_level,
  CASE
    WHEN (i.stock_on_hand - i.allocated_stock) <= i.reorder_level THEN TRUE
    ELSE FALSE
  END AS is_low_stock
FROM fast_movers fm
INNER JOIN products p ON p.product_id = fm.product_id
INNER JOIN inventory i ON i.product_id = p.product_id
ORDER BY fm.units_sold DESC, p.product_id, i.warehouse_name
LIMIT {row_limit}"""


def _high_credit_outstanding_sql(row_limit: int) -> str:
    return f"""SELECT
  customer_id,
  company_name,
  contact_name,
  email,
  phone,
  credit_limit,
  outstanding_balance
FROM customers
WHERE credit_limit > 500000
  AND outstanding_balance > 0
LIMIT {row_limit}"""


def _high_credit_limit_sql(min_credit: int, row_limit: int) -> str:
    return f"""SELECT
  customer_id,
  company_name,
  contact_name,
  email,
  phone,
  credit_limit,
  outstanding_balance
FROM customers
WHERE credit_limit >= {min_credit}
ORDER BY credit_limit DESC
LIMIT {row_limit}"""


def _top_selling_products_sql(year: int, top_n: int) -> str:
    """Top N products by units sold (includes product_name)."""
    next_year = year + 1
    return f"""SELECT
  p.product_id,
  p.sku,
  p.product_name,
  SUM(oi.quantity) AS units_sold
FROM order_items oi
INNER JOIN products p ON p.product_id = oi.product_id
INNER JOIN sales_orders so ON so.order_id = oi.order_id
WHERE so.order_date >= '{year}-01-01' AND so.order_date < '{next_year}-01-01'
  AND so.status NOT IN ('Draft', 'Cancelled')
GROUP BY p.product_id, p.sku, p.product_name
ORDER BY units_sold DESC
LIMIT {top_n}"""


def _top_products_by_revenue_sql(year: int, top_n: int) -> str:
    """Top N products by revenue (line totals)."""
    next_year = year + 1
    return f"""SELECT
  p.product_id,
  p.sku,
  p.product_name,
  SUM(oi.line_total) AS total_revenue
FROM order_items oi
INNER JOIN products p ON p.product_id = oi.product_id
INNER JOIN sales_orders so ON so.order_id = oi.order_id
WHERE so.order_date >= '{year}-01-01' AND so.order_date < '{next_year}-01-01'
  AND so.status NOT IN ('Draft', 'Cancelled')
GROUP BY p.product_id, p.sku, p.product_name
ORDER BY total_revenue DESC
LIMIT {top_n}"""


def _items_below_reorder_sql(row_limit: int) -> str:
    """Products/warehouse rows where available stock is at or below reorder level."""
    return f"""SELECT
  p.product_id,
  p.sku,
  p.product_name,
  i.warehouse_name,
  i.stock_on_hand,
  i.allocated_stock,
  i.stock_on_hand - i.allocated_stock AS available_stock,
  i.reorder_level
FROM products p
INNER JOIN inventory i ON i.product_id = p.product_id
WHERE (i.stock_on_hand - i.allocated_stock) <= i.reorder_level
ORDER BY available_stock ASC, p.product_name, i.warehouse_name
LIMIT {row_limit}"""


_LOW_STOCK_THRESHOLD_RE = re.compile(
    r"\b("
    r"below\s+(?:the\s+)?reorder|"
    r"under\s+(?:the\s+)?reorder|"
    r"low\s+stock|"
    r"out\s+of\s+stock|"
    r"reorder\s+level"
    r")\b",
    re.IGNORECASE,
)

_LISTING_INVENTORY_RE = re.compile(
    r"\b(?:which|what)\s+(?:item|items|product|products|sku|skus)\b",
    re.IGNORECASE,
)


def query_is_low_stock_threshold(user_query: str) -> bool:
    """True for inventory threshold questions, not named warehouse/SKU lookups."""
    text = user_query.strip()
    if not text:
        return False
    if _LOW_STOCK_THRESHOLD_RE.search(text):
        return True
    lower = text.lower()
    if _LISTING_INVENTORY_RE.search(text) and (
        "reorder" in lower or "low stock" in lower or "low on stock" in lower
    ):
        return True
    return False


def _sku_stock_sql(sku: str, row_limit: int) -> str:
    safe_sku = re.sub(r"[^A-Za-z0-9\-]", "", sku)
    return f"""SELECT
  p.product_id,
  p.sku,
  p.product_name,
  i.warehouse_name,
  i.stock_on_hand,
  i.allocated_stock,
  i.stock_on_hand - i.allocated_stock AS available_stock,
  i.reorder_level
FROM products p
INNER JOIN inventory i ON i.product_id = p.product_id
WHERE p.sku = '{safe_sku}'
ORDER BY i.warehouse_name
LIMIT {row_limit}"""


def _query_is_top_ranking(user_query: str) -> bool:
    q = user_query.lower()
    return bool(re.search(r"\btop\s+\d+\b", q))


def _query_is_top_selling(user_query: str) -> bool:
    q = user_query.lower()
    if "revenue" in q:
        return False
    return any(
        word in q
        for word in (
            "selling",
            "seller",
            "sold",
            "best seller",
            "best-selling",
            "fast-moving",
            "fast moving",
            "fast mover",
            "units sold",
        )
    )


def resolve_ad_hoc_template_sql(user_query: str, year: int) -> str | None:
    """SINGLE-mode templates from the full user question."""
    extremum_sql = try_extremum_template_sql(user_query, year=year, row_limit=1)
    if extremum_sql:
        return extremum_sql

    if query_is_low_stock_threshold(user_query):
        return _items_below_reorder_sql(SQL_ROW_LIMIT)

    if not _query_is_top_ranking(user_query):
        return None
    top_n = parse_rank_limit(user_query) or 3
    q = user_query.lower()
    if "revenue" in q:
        return _top_products_by_revenue_sql(year, top_n)
    if _query_is_top_selling(user_query) or "product" in q:
        return _top_selling_products_sql(year, top_n)
    return None


def resolve_template_sql(target: QueryTarget | None, year: int) -> str | None:
    """Return canonical SQL for known target ids; None to use LLM."""
    if target is None:
        return None

    tid = target.id.lower()
    tables = {t.lower() for t in target.tables}
    intent = (target.intent or "").lower()
    label = (target.label or "").lower()

    if tid in ("high_credit_outstanding", "credit_parties", "high_credit_parties"):
        return _high_credit_outstanding_sql(SQL_ROW_LIMIT)

    credit_limit_only = tid in (
        "high_credit_customers",
        "high_credit_limit",
        "credit_limit_customers",
    ) or (
        tables == {"customers"}
        and "credit" in intent
        and "outstanding" not in intent
        and "sku" not in intent
    )
    if credit_limit_only:
        threshold = parse_credit_threshold(f"{intent} {label}")
        return _high_credit_limit_sql(threshold, SQL_ROW_LIMIT)

    sku = parse_sku(f"{intent} {label}")
    sku_stock = tid in ("sku_stock_by_warehouse", "sku_stock", "sku_inventory") or (
        {"products", "inventory"}.issubset(tables) and sku is not None
    )
    if sku_stock and sku:
        return _sku_stock_sql(sku, SQL_ROW_LIMIT)

    fast_stock = (
        "fast" in tid
        and ("stock" in tid or "mov" in tid or "invent" in tid)
    ) or (
        {"order_items", "inventory", "products"}.issubset(tables)
        and ("fast" in intent or "fast" in label)
        and ("stock" in intent or "stock" in label or "low" in intent)
    )
    if fast_stock:
        return _fast_movers_low_stock_sql(year, SQL_ROW_LIMIT)

    low_stock = tid in (
        "low_stock_items",
        "items_below_reorder",
        "below_reorder_level",
    ) or (
        {"products", "inventory"}.issubset(tables)
        and query_is_low_stock_threshold(f"{intent} {label}")
    )
    if low_stock:
        return _items_below_reorder_sql(SQL_ROW_LIMIT)

    return None
