"""Tests for entity extractor gating."""

from app.planning.entity_extract_gate import (
    is_entity_spec_allowed,
    should_skip_entity_extractor,
)
from app.sql.entity_match_sql import EntityFilterSpec


def test_skip_entity_extractor_for_salary_query():
    assert should_skip_entity_extractor("What is the salary for Diya Sharma?")


def test_skip_entity_extractor_for_employee_keyword():
    assert should_skip_entity_extractor("List job title for employees in sales")


def test_do_not_skip_warehouse_stock_query():
    assert not should_skip_entity_extractor(
        "What is the current stock level of Mumbai Warehouse?"
    )


def test_skip_entity_extractor_for_product_attribute_lookup():
    assert should_skip_entity_extractor("What is the unit price for Widget Pro?")
    assert should_skip_entity_extractor("What is the category for SKU-1008-530 ?")


def test_reject_product_spec_for_salary_query():
    spec = EntityFilterSpec(
        query_kind="product_lookup",
        parameter="product_name",
        table="products",
        column="product_name",
        phrase="Diya Sharma",
    )
    assert not is_entity_spec_allowed("What is the salary for Diya Sharma?", spec)


def test_allow_warehouse_spec_for_stock_query():
    spec = EntityFilterSpec(
        query_kind="warehouse_stock",
        parameter="warehouse_name",
        table="inventory",
        column="warehouse_name",
        phrase="Mumbai Warehouse",
    )
    assert is_entity_spec_allowed(
        "What is stock at Mumbai Warehouse?",
        spec,
    )


def test_skip_entity_extractor_for_below_reorder_query():
    q = "Which item is currently below reorder level ?"
    assert should_skip_entity_extractor(q)


def test_reject_condition_phrase_entity_spec():
    spec = EntityFilterSpec(
        query_kind="warehouse_stock",
        parameter="warehouse_name",
        table="inventory",
        column="warehouse_name",
        phrase="below reorder level",
    )
    assert not is_entity_spec_allowed(
        "Which item is currently below reorder level ?",
        spec,
    )
