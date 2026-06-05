"""SQL template resolution tests."""

from app.contracts.targets import QueryTarget
from app.sql.target_templates import resolve_ad_hoc_template_sql, resolve_template_sql
from app.validator.sql_validator import validate_sql


def test_fast_movers_template_validates():
    target = QueryTarget(
        id="fast_movers_low_stock",
        label="Top 3 fast movers low stock",
        tables=["order_items", "sales_orders", "products", "inventory"],
        intent="Check low stock for top 3 fast moving products",
    )
    sql = resolve_template_sql(target, 2026)
    assert sql is not None
    assert "WITH fast_movers AS" in sql
    assert "is_low_stock" in sql
    assert "WHERE (i.stock_on_hand" not in sql
    assert "top_products" not in sql.lower()
    result = validate_sql(sql)
    assert result.passed
    assert result.schema_ok


def test_top_selling_products_ad_hoc_template():
    sql = resolve_ad_hoc_template_sql("Top 3 selling products", 2026)
    assert sql is not None
    assert "product_name" in sql
    assert "units_sold" in sql
    assert "LIMIT 3" in sql
    assert "total_quantity" not in sql.lower()
    result = validate_sql(sql)
    assert result.passed


def test_top_revenue_ad_hoc_template():
    sql = resolve_ad_hoc_template_sql("Top 3 products by revenue", 2026)
    assert sql is not None
    assert "total_revenue" in sql
    assert "product_name" in sql
    assert "LIMIT 3" in sql
    result = validate_sql(sql)
    assert result.passed


def test_high_credit_limit_template_validates():
    target = QueryTarget(
        id="high_credit_customers",
        label="High credit customers",
        tables=["customers"],
        intent="credit_limit >= 2500000",
    )
    sql = resolve_template_sql(target, 2026)
    assert sql is not None
    assert "credit_limit >= 2500000" in sql
    assert "outstanding_balance > 0" not in sql
    result = validate_sql(sql)
    assert result.passed


def test_sku_stock_template_validates():
    target = QueryTarget(
        id="sku_stock_by_warehouse",
        label="SKU stock",
        tables=["products", "inventory"],
        intent="Stock for SKU-1001-363 by warehouse",
    )
    sql = resolve_template_sql(target, 2026)
    assert sql is not None
    assert "p.sku = 'SKU-1001-363'" in sql
    assert "warehouse_name" in sql
    assert "customers" not in sql
    result = validate_sql(sql)
    assert result.passed


def test_high_credit_template_validates():
    target = QueryTarget(
        id="high_credit_outstanding",
        label="High credit with balance",
        tables=["customers"],
        intent="credit_limit > 500000",
    )
    sql = resolve_template_sql(target, 2026)
    assert sql is not None
    result = validate_sql(sql)
    assert result.passed


def test_below_reorder_ad_hoc_template():
    sql = resolve_ad_hoc_template_sql(
        "Which item is currently below reorder level ?",
        2026,
    )
    assert sql is not None
    assert "strict_word_similarity" not in sql.lower()
    assert "reorder_level" in sql
    assert "stock_on_hand - i.allocated_stock" in sql
    assert "<= i.reorder_level" in sql
    assert "product_name" in sql
    result = validate_sql(sql)
    assert result.passed


def test_low_stock_target_template():
    target = QueryTarget(
        id="low_stock_items",
        label="Items below reorder",
        tables=["products", "inventory"],
        intent="available stock at or below reorder level",
    )
    sql = resolve_template_sql(target, 2026)
    assert sql is not None
    assert "<= i.reorder_level" in sql
    result = validate_sql(sql)
    assert result.passed
