"""Tests for evidence-grounded scalar insights."""

from app.insights.grounding import (
    build_grounded_insight,
    build_ranked_list_insight,
    extract_verified_facts,
    sanitize_insight_text,
    try_empty_rows_insight,
    try_extremum_insight,
    try_grounded_insight,
    try_ranked_list_insight,
)


def test_extract_verified_facts_single_aggregate_row():
    rows = [{"sum": "28567207.08"}]
    facts = extract_verified_facts(rows)
    assert facts["sum"] == 28567207.08


def test_grounded_insight_revenue_query():
    rows = [{"sum": 28567207.08}]
    insight = try_grounded_insight("What is total revenue in 2026?", rows)
    assert insight == "Total revenue in 2026 is 28567207.08."


def test_grounded_insight_warehouse_count():
    rows = [{"count": 3}]
    insight = try_grounded_insight("How many warehouses are there?", rows)
    assert insight == "There are 3 warehouses."
    assert "3.00" not in insight
    assert "Count is" not in insight


def test_grounded_insight_singular_count():
    rows = [{"count": 1}]
    insight = try_grounded_insight("How many warehouses are there?", rows)
    assert insight == "There is 1 warehouse."


def test_grounded_insight_skips_multi_row():
    rows = [{"order_id": 1}, {"order_id": 2}]
    assert try_grounded_insight("List orders", rows) is None


def test_build_grounded_insight_multiple_metrics():
    text = build_grounded_insight(
        "Show totals",
        {"sum": 100.5, "count": 3},
    )
    assert "100.50" in text
    assert "Count is 3" in text
    assert "3.00" not in text


def test_ranked_list_insight_top_products_by_revenue():
    rows = [
        {"product_name": "SecureGate Firewall Router v36.0", "revenue": 308873.72},
        {"product_name": "PrimeCMS Enterprise License v485.0", "revenue": 295431.04},
        {"product_name": "DSBackup Cloud Node v454.0", "revenue": 279550.73},
    ]
    insight = try_ranked_list_insight("Top 3 products by revenue", rows)
    assert insight is not None
    assert "Top 3 products by revenue:" in insight
    assert "SecureGate" in insight
    assert "308873.72" in insight
    assert "sample rows" not in insight.lower()


def test_ranked_list_insight_respects_top_n_when_sql_returns_more():
    many_rows = [
        {"product_name": f"Product {i}", "revenue": 1000.0 - i}
        for i in range(20)
    ]
    insight = try_ranked_list_insight("Top 3 products by revenue", many_rows)
    assert insight is not None
    assert "1. Product 0" in insight
    assert "3. Product 2" in insight
    assert "4. Product" not in insight
    assert "Product 19" not in insight


def test_ranked_list_selling_products_with_names():
    rows = [
        {
            "product_id": 36,
            "product_name": "SecureGate Firewall Router v36.0",
            "units_sold": 1842,
        },
        {
            "product_id": 485,
            "product_name": "PrimeCMS Enterprise License v485.0",
            "units_sold": 1750,
        },
        {
            "product_id": 454,
            "product_name": "DSBackup Cloud Node v454.0",
            "units_sold": 1600,
        },
    ]
    insight = try_ranked_list_insight("Top 3 selling products", rows)
    assert insight is not None
    assert "SecureGate" in insight
    assert "units sold 1842.00" in insight
    assert "Unknown" not in insight


def test_ranked_list_fallback_product_id_when_name_missing():
    rows = [
        {"product_id": 36, "total_quantity": 100},
        {"product_id": 143, "total_quantity": 90},
    ]
    insight = try_ranked_list_insight("Top 2 selling products", rows)
    assert "Product ID 36" in insight
    assert "units sold" in insight


def test_sanitize_insight_strips_meta_prefix():
    raw = (
        "Based on the provided database sample rows, the top 3 products by revenue are:\n\n"
        "1. Alpha — revenue 100.00"
    )
    cleaned = sanitize_insight_text(raw)
    assert "sample rows" not in cleaned.lower()
    assert cleaned.startswith("the top 3") or cleaned.startswith("1.")


def test_empty_rows_insight_no_hallucination_path():
    insight = try_empty_rows_insight("What is the salary for Diya Sharma?", [])
    assert insight is not None
    assert "No records matched" in insight
    assert "85000" not in insight


def test_empty_rows_insight_none_when_rows_present():
    assert try_empty_rows_insight("What is revenue?", [{"sum": 1}]) is None


def test_extremum_insight_order_highest_tax():
    insight = try_extremum_insight(
        "Which order has highest tax amount ?",
        [{"order_id": 696, "tax_amount": 1520.75}],
    )
    assert insight is not None
    assert "Order 696" in insight
    assert "highest" in insight
    assert "tax amount" in insight
    assert "1520.75" in insight


def test_extremum_insight_order_id_only():
    insight = try_extremum_insight(
        "Which order has highest tax amount ?",
        [{"order_id": 696}],
    )
    assert insight == "Order 696 has the highest tax amount."


def test_extremum_insight_least_wording():
    insight = try_extremum_insight(
        "Which order has least tax amount ?",
        [{"order_id": 42, "tax_amount": 100.0}],
    )
    assert insight is not None
    assert "lowest" in insight
    assert "Order 42" in insight
