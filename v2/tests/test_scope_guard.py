"""Out-of-scope query guard tests."""

from app.planning.scope_guard import (
    OUT_OF_SCOPE_USER_MESSAGE,
    is_likely_in_scope,
    is_planner_parse_failure_out_of_scope,
    is_planner_prose_refusal,
)
from app.schema.scope_vocabulary import (
    looks_like_entity_record_lookup,
    query_has_sku_reference,
    query_matches_scope_vocabulary,
)


def test_what_is_google_out_of_scope():
    assert is_likely_in_scope("What is Google?") is False


def test_revenue_question_in_scope():
    assert is_likely_in_scope("What is total revenue in 2026?") is True
    assert is_likely_in_scope("Top 3 products by revenue") is True


def test_product_category_by_sku_in_scope():
    q = "What is the category of SKU-1001-363 ?"
    assert query_has_sku_reference(q)
    assert is_likely_in_scope(q) is True


def test_product_price_by_name_in_scope():
    q = "What is the price for PrimeCMS Enterprise License v1.0 ?"
    assert query_matches_scope_vocabulary(q)
    assert looks_like_entity_record_lookup(q)
    assert is_likely_in_scope(q) is True


def test_product_category_by_name_in_scope():
    q = "What is the category of PrimeCMS Enterprise License v1.0 ?"
    assert query_matches_scope_vocabulary(q)
    assert looks_like_entity_record_lookup(q)
    assert is_likely_in_scope(q) is True


def test_planner_prose_refusal_detected():
    raw = "I'm not able to provide information about that. Please ask a business analytics request."
    assert is_planner_prose_refusal(raw) is True
    assert is_planner_parse_failure_out_of_scope(raw, "What is Google?") is True


def test_user_message_constant():
    assert "business-related" in OUT_OF_SCOPE_USER_MESSAGE.lower()
