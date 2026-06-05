"""Tests for schema-driven attribute lookup SQL."""

from app.insights.grounding import (
    try_boolean_attribute_insight,
    try_text_attribute_insight,
)
from app.planning.attribute_lookup import (
    extract_entity_phrase,
    expects_single_entity_answer,
    is_attribute_lookup_query,
    is_inventory_stock_query,
    parse_attribute_lookup_intent,
    resolve_boolean_attribute,
    resolve_requested_attribute,
    try_attribute_lookup_sql,
)
from app.planning.disambiguation import build_resolved_entity_sql, evaluate_disambiguation
from app.planning.entity_extract_gate import (
    is_entity_spec_allowed,
    should_skip_entity_extractor,
)
from app.sql.entity_match_sql import EntityFilterSpec


def test_resolve_category_attribute():
    assert resolve_requested_attribute(
        "What is the category for SKU-1008-530 ?"
    ) == ("products", "category")


def test_resolve_price_alias():
    assert resolve_requested_attribute(
        "What is the price for PrimeCMS Enterprise License v1.0 ?"
    ) == ("products", "unit_price")


def test_sku_category_sql_exact_products_only():
    sql = try_attribute_lookup_sql("What is the category for SKU-1008-530 ?")
    assert sql is not None
    assert "FROM public.products" in sql
    assert "category" in sql
    assert "sku = 'SKU-1008-530'" in sql
    assert "inventory" not in sql.lower()
    assert "warehouse_name" not in sql.lower()


def test_stock_query_not_attribute_lookup():
    assert is_inventory_stock_query("What is stock for SKU-1008-530 at Mumbai?")
    assert not is_attribute_lookup_query("What is stock for SKU-1008-530?")


def test_skip_entity_extractor_for_category_by_sku():
    q = "What is the category for SKU-1008-530 ?"
    assert should_skip_entity_extractor(q)
    spec = EntityFilterSpec(
        query_kind="sku_stock",
        parameter="sku",
        table="products",
        column="sku",
        phrase="SKU-1008-530",
    )
    assert not is_entity_spec_allowed(q, spec)


def test_text_attribute_insight():
    insight = try_text_attribute_insight(
        "What is the category for SKU-1008-530 ?",
        [{"category": "Software"}],
    )
    assert insight == "The category for SKU-1008-530 is Software."


def test_disambiguation_skipped_for_sku_category():
    rows = [{"category": "Software"}, {"category": "Software"}]
    payload = evaluate_disambiguation(
        "What is the category for SKU-1008-530 ?",
        rows,
        "SELECT category FROM products WHERE sku = 'SKU-1008-530'",
        {},
    )
    assert payload is None


def test_parse_intent_fields():
    intent = parse_attribute_lookup_intent("What is the category for SKU-1008-530 ?")
    assert intent is not None
    assert intent.table == "products"
    assert intent.attribute_column == "category"
    assert intent.filter_column == "sku"
    assert intent.filter_value == "SKU-1008-530"
    assert intent.match_mode == "exact"


def test_resolve_boolean_discontinued_attribute():
    assert resolve_boolean_attribute("Is PrimeCMS discontinued?") == (
        "products",
        "is_discontinued",
    )
    assert resolve_requested_attribute("Is PrimeCMS discontinued?") == (
        "products",
        "is_discontinued",
    )


def test_boolean_discontinued_sql_includes_pk_and_attribute():
    sql = try_attribute_lookup_sql("Is PrimeCMS discontinued?")
    assert sql is not None
    assert "product_id" in sql
    assert "product_name" in sql
    assert "is_discontinued" in sql
    assert "strict_word_similarity('PrimeCMS', product_name)" in sql
    assert "inventory" not in sql.lower()


def test_extract_entity_phrase_from_is_question():
    assert extract_entity_phrase("Is PrimeCMS discontinued?") == "PrimeCMS"


def test_expects_single_entity_for_boolean_question():
    assert expects_single_entity_answer("Is PrimeCMS discontinued?")
    assert should_skip_entity_extractor("Is PrimeCMS discontinued?")


def test_boolean_insight_single_row():
    insight = try_boolean_attribute_insight(
        "Is PrimeCMS discontinued?",
        [
            {
                "product_id": 485,
                "product_name": "PrimeCMS Enterprise License v485.0",
                "is_discontinued": True,
            }
        ],
    )
    assert insight == "PrimeCMS Enterprise License v485.0 is discontinued."


def test_disambiguation_for_boolean_multi_match():
    sql = try_attribute_lookup_sql("Is PrimeCMS discontinued?")
    assert sql is not None
    rows = [
        {
            "product_id": 485,
            "product_name": "PrimeCMS Enterprise License v485.0",
            "is_discontinued": True,
            "match_score": 0.9,
        },
        {
            "product_id": 1,
            "product_name": "PrimeCMS Starter v1.0",
            "is_discontinued": False,
            "match_score": 0.85,
        },
    ]
    payload = evaluate_disambiguation(
        "Is PrimeCMS discontinued?",
        rows,
        sql,
        {},
    )
    assert payload is not None
    assert payload.parameter == "product_id"
    assert payload.original_phrase == "PrimeCMS"
    assert len(payload.options) == 2
    assert "match_score" not in payload.message
    assert "Please select" in payload.message


def test_resolved_boolean_follow_up_sql():
    sql = build_resolved_entity_sql(
        "Is PrimeCMS discontinued?",
        {"product_id": "485"},
        try_attribute_lookup_sql("Is PrimeCMS discontinued?"),
    )
    assert sql is not None
    assert "product_id = '485'" in sql
    assert "is_discontinued" in sql


def test_order_status_sql_uses_exact_numeric_id():
    sql = try_attribute_lookup_sql("What is the status of Order No 408 ?")
    assert sql is not None
    assert "order_id = 408" in sql
    assert "strict_word_similarity" not in sql.lower()
    assert "status" in sql


def test_order_status_intent():
    intent = parse_attribute_lookup_intent("What is the status of Order 408 ?")
    assert intent is not None
    assert intent.table == "sales_orders"
    assert intent.attribute_column == "status"
    assert intent.filter_column == "order_id"
    assert intent.filter_value == "408"
    assert intent.match_mode == "exact"
    assert intent.filter_value_is_numeric
