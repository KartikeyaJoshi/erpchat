"""Offline SQL validator tests."""

from app.validator.sql_validator import normalize_sql_for_execution, validate_sql


def test_valid_simple_select():
    sql = """
    SELECT so.order_id, so.total_amount
    FROM sales_orders so
    WHERE so.status = 'Paid'
    LIMIT 100
    """
    result = validate_sql(sql)
    assert result.passed
    assert result.syntax_ok
    assert result.schema_ok


def test_rejects_unknown_table():
    sql = "SELECT id FROM phantom_orders LIMIT 10"
    result = validate_sql(sql)
    assert not result.passed
    assert not result.schema_ok
    assert any("Unknown tables" in i for i in result.issues)


def test_rejects_write_operations():
    sql = "DELETE FROM sales_orders WHERE order_id = 1"
    result = validate_sql(sql)
    assert not result.passed
    assert not result.policy_ok


def test_rejects_invalid_syntax():
    result = validate_sql("SELECT FROM WHERE")
    assert not result.passed
    assert not result.syntax_ok


def test_normalize_strips_trailing_semicolon():
    sql = (
        "SELECT SUM(subtotal) FROM public.sales_orders "
        "WHERE status NOT IN ('Draft', 'Cancelled');"
    )
    normalized = normalize_sql_for_execution(sql)
    assert not normalized.endswith(";")
    assert "SUM" in normalized.upper()


def test_normalize_injects_limit_when_missing():
    sql = "SELECT order_id FROM sales_orders WHERE status = 'Paid'"
    normalized = normalize_sql_for_execution(sql, row_limit=50)
    assert "LIMIT 50" in normalized.upper()
    assert not normalized.endswith(";")


def test_normalize_preserves_existing_limit():
    sql = "SELECT order_id FROM sales_orders LIMIT 10"
    normalized = normalize_sql_for_execution(sql)
    assert "LIMIT 10" in normalized.upper()
    assert "LIMIT 1000" not in normalized.upper()


def test_rejects_similarity_on_numeric_order_id():
    sql = (
        "SELECT order_id, status, "
        "strict_word_similarity('Order 408', order_id) AS match_score "
        "FROM sales_orders "
        "WHERE strict_word_similarity('Order 408', order_id) >= 0.4 "
        "LIMIT 10"
    )
    result = validate_sql(sql)
    assert not result.passed
    assert not result.policy_ok
    assert any("strict_word_similarity" in i for i in result.issues)


def test_allows_similarity_on_product_name():
    sql = (
        "SELECT product_name, strict_word_similarity('PrimeCMS', product_name) AS match_score "
        "FROM products "
        "WHERE strict_word_similarity('PrimeCMS', product_name) >= 0.4 "
        "LIMIT 10"
    )
    result = validate_sql(sql)
    assert result.passed
