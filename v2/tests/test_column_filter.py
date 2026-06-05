"""Tests for schema-driven column filter strategies."""

from app.schema.column_filter import (
    allows_fuzzy_match,
    column_filter_kind,
)
from app.planning.record_reference import (
    extract_numeric_reference,
    resolve_record_filter,
)
from app.schema.entity_metadata import get_entity_metadata


def test_order_id_is_exact_numeric():
    assert column_filter_kind("sales_orders", "order_id") == "exact_numeric"
    assert not allows_fuzzy_match("sales_orders", "order_id")


def test_product_name_is_fuzzy():
    assert column_filter_kind("products", "product_name") == "fuzzy_text"
    assert allows_fuzzy_match("products", "product_name")


def test_sku_is_exact_code():
    assert column_filter_kind("products", "sku") == "exact_code"


def test_extract_order_number_from_phrase():
    assert extract_numeric_reference("Order No 408", noun="order") == "408"
    assert extract_numeric_reference("Order 408") == "408"
    assert extract_numeric_reference("408") == "408"


def test_resolve_order_status_filter():
    entity = get_entity_metadata("sales_orders")
    assert entity is not None
    record = resolve_record_filter(
        "sales_orders",
        phrase="Order No 408",
        sku=None,
        entity=entity,
    )
    assert record is not None
    assert record.column == "order_id"
    assert record.value == "408"
    assert record.match_mode == "exact"
    assert record.value_is_numeric


def test_resolve_product_name_fuzzy():
    entity = get_entity_metadata("products")
    assert entity is not None
    record = resolve_record_filter(
        "products",
        phrase="PrimeCMS Enterprise License v485.0",
        sku=None,
        entity=entity,
    )
    assert record is not None
    assert record.column == "product_name"
    assert record.match_mode == "similarity"


def test_resolve_sku_exact():
    entity = get_entity_metadata("products")
    assert entity is not None
    record = resolve_record_filter(
        "products",
        phrase="SKU-1008-530",
        sku="SKU-1008-530",
        entity=entity,
    )
    assert record is not None
    assert record.column == "sku"
    assert record.match_mode == "exact"
