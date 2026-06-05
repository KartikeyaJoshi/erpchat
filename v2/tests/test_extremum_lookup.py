"""Tests for schema-driven extremum (highest/lowest) SQL templates."""

from app.insights.grounding import try_extremum_insight
from app.planning.extremum_lookup import (
    parse_extremum_intent,
    query_is_single_extremum,
    try_extremum_template_sql,
)
from app.sql.target_templates import resolve_ad_hoc_template_sql
from app.validator.sql_validator import validate_sql


def test_query_is_single_extremum_least_tax():
    q = "Which order has least tax amount ?"
    assert query_is_single_extremum(q)
    assert parse_extremum_intent(q) is not None


def test_extremum_sql_least_tax_simple():
    sql = try_extremum_template_sql("Which order has least tax amount ?", year=2026)
    assert sql is not None
    assert "FROM public.sales_orders" in sql
    assert "order_id" in sql
    assert "tax_amount" in sql
    assert "ORDER BY tax_amount ASC" in sql
    assert "LIMIT 1" in sql
    assert "order_items" not in sql.lower()
    assert "extract(year" not in sql.lower()
    assert "with " not in sql.lower()
    result = validate_sql(sql)
    assert result.passed


def test_extremum_sql_highest_tax_desc():
    sql = try_extremum_template_sql("Which order has highest tax amount ?", year=2026)
    assert sql is not None
    assert "ORDER BY tax_amount DESC" in sql


def test_ad_hoc_resolves_extremum_before_top_n():
    sql = resolve_ad_hoc_template_sql("Which order has least tax amount ?", 2026)
    assert sql is not None
    assert "sales_orders" in sql
    assert "ORDER BY tax_amount ASC" in sql


def test_extremum_applies_year_when_asked():
    sql = try_extremum_template_sql(
        "Which order has least tax amount in 2025 ?",
        year=2026,
    )
    assert sql is not None
    assert "order_date >= '2025-01-01'" in sql
    assert "order_date < '2026-01-01'" in sql


def test_extremum_insight_least_tax():
    insight = try_extremum_insight(
        "Which order has least tax amount ?",
        [{"order_id": 42, "tax_amount": 1257.3}],
    )
    assert insight is not None
    assert "Order 42" in insight
    assert "lowest" in insight
    assert "tax amount" in insight
    assert "1257.30" in insight
