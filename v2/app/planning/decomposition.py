"""Heuristic multi-question detection when the LLM planner returns SINGLE mode."""

from __future__ import annotations

import re

from app.contracts.targets import QueryTarget

_TOP_N_RE = re.compile(
    r"\b(?:top|bottom|first|last)\s+(\d+)\b",
    re.IGNORECASE,
)


def parse_rank_limit(user_query: str) -> int | None:
    """Extract N from phrases like 'top 3' or 'bottom 5'."""
    match = _TOP_N_RE.search(user_query)
    if match:
        return int(match.group(1))
    return None


def parse_credit_threshold(text: str, default: int = 500_000) -> int:
    """Extract credit_limit threshold from user text (e.g. 2500000, 25 lakhs)."""
    lower = text.lower()
    lakh_match = re.search(r"(\d+(?:\.\d+)?)\s*lakhs?", lower)
    if lakh_match:
        return int(float(lakh_match.group(1)) * 100_000)

    gte = re.search(
        r"credit[\s_]*limit\s*(?:of\s*)?(?:>=|above|over)\s*(\d[\d,]*(?:\.\d+)?)",
        text,
        re.IGNORECASE,
    )
    if gte:
        return int(float(gte.group(1).replace(",", "")))

    explicit = re.search(
        r"credit[\s_]*limit\s*(?:of\s*)?(\d[\d,]*(?:\.\d+)?)",
        text,
        re.IGNORECASE,
    )
    if explicit:
        return int(float(explicit.group(1).replace(",", "")))

    above = re.search(r"(\d[\d,]*)\s*(?:and\s+)?above", text, re.IGNORECASE)
    if above:
        return int(above.group(1).replace(",", ""))

    return default


def parse_sku(text: str) -> str | None:
    """Extract SKU token (e.g. SKU-1001-363). Prefers hyphenated SKU-xxx over bare 'SKU'."""
    matches = re.findall(r"SKU-[A-Za-z0-9\-]+", text, re.IGNORECASE)
    if not matches:
        return None
    sku = max(matches, key=len).upper()
    while sku.startswith("SKU-SKU-"):
        sku = "SKU-" + sku[8:]
    return sku


def _mentions_credit_customers(query: str) -> bool:
    q = query.lower()
    return (
        "credit limit" in q
        or "credit_limit" in q
        or ("credit" in q and "customer" in q)
        or ("lakhs" in q and "credit" in q)
    )


def _mentions_sku_stock(query: str) -> bool:
    q = query.lower()
    return bool(parse_sku(query)) or (
        ("stock" in q or "inventory" in q) and ("sku" in q or "warehouse" in q)
    )


def try_heuristic_multi_step(user_query: str) -> list[QueryTarget] | None:
    """
    Build targets for common dual asks (credit customers + SKU stock) when the
    planner did not emit MULTI_STEP.
    """
    query = user_query.strip()
    if not query:
        return None

    q_lower = query.lower()
    has_also = bool(re.search(r"\b(?:and\s+)?also\b", q_lower))
    credit = _mentions_credit_customers(query)
    sku_stock = _mentions_sku_stock(query)

    if not (credit and sku_stock):
        return None

    # Require an explicit second clause or strong dual-domain signal
    if not has_also and not (credit and sku_stock and parse_sku(query)):
        return None

    threshold = parse_credit_threshold(query)
    sku = parse_sku(query)
    if not sku:
        return None

    return [
        QueryTarget(
            id="high_credit_customers",
            label="Customers at or above the requested credit limit",
            tables=["customers"],
            intent=(
                f"List all customers where credit_limit >= {threshold} "
                "(include company_name and credit_limit)."
            ),
        ),
        QueryTarget(
            id="sku_stock_by_warehouse",
            label=f"Stock levels for {sku} by warehouse",
            tables=["products", "inventory"],
            intent=(
                f"Return stock_on_hand, allocated_stock, available stock, reorder_level, "
                f"and warehouse_name for products.sku = '{sku}'."
            ),
        ),
    ]
