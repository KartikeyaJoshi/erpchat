"""Tests for schema-derived scope vocabulary."""

from app.schema.scope_vocabulary import (
    looks_like_entity_record_lookup,
    query_has_sku_reference,
    query_matches_scope_vocabulary,
    scope_vocabulary,
)


def test_scope_vocabulary_includes_product_columns():
    terms = scope_vocabulary()
    assert "category" in terms
    assert "unit_price" in terms or "price" in terms
    assert "sku" in terms


def test_sku_pattern_detected():
    assert query_has_sku_reference("What is the category of SKU-1001-363?")


def test_entity_lookup_detects_price_for_product():
    assert looks_like_entity_record_lookup(
        "What is the price for PrimeCMS Enterprise License v1.0?"
    )


def test_general_trivia_not_entity_lookup():
    assert not looks_like_entity_record_lookup("What is Google?")
    assert not query_matches_scope_vocabulary("What is Google?")
