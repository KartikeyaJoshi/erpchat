"""Tests for Python analyzer bypass when SQL already answers the question."""

from app.main import _python_error_is_non_blocking
from app.planning.python_bypass import should_bypass_python_analyzer


def test_bypass_extremum_query_single_row():
    q = "Which order has highest tax amount ?"
    rows = [{"order_id": 696}]
    assert should_bypass_python_analyzer(
        q,
        rows,
        sql="SELECT order_id FROM sales_orders WHERE tax_amount = (SELECT MAX(tax_amount) FROM sales_orders) LIMIT 10",
        execution_category="COMPLEX_ANALYSIS",
    )


def test_bypass_direct_query_category():
    assert should_bypass_python_analyzer(
        "What is total revenue?",
        [{"sum": 100.0}],
        execution_category="DIRECT_QUERY",
    )


def test_no_bypass_multi_step():
    assert not should_bypass_python_analyzer(
        "Which order has highest tax amount ?",
        [{"order_id": 696}],
        query_mode="MULTI_STEP",
        execution_category="COMPLEX_ANALYSIS",
    )


def test_python_error_non_blocking_when_insight_present():
    assert _python_error_is_non_blocking(
        python_out={"error": "invalid syntax"},
        insight_text="Order 696 has the highest tax amount.",
        partial_pipeline=False,
        has_failed_target=False,
        row_count=1,
    )


def test_python_error_blocking_without_insight():
    assert not _python_error_is_non_blocking(
        python_out={"error": "invalid syntax"},
        insight_text="",
        partial_pipeline=False,
        has_failed_target=False,
        row_count=1,
    )
