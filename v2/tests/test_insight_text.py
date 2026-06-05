"""Insight copy tests."""

from app.insights.grounding import build_multi_target_insight, try_multi_target_insight

CREDIT_STOCK_QUERY = (
    "Which parties have a credit limit above 5 Lakhs but still have an outstanding "
    "balance? Also, check if any of our top 3 fast-moving items are currently running "
    "low on stock across our warehouses."
)


def test_fast_movers_lists_top_three_even_when_not_low():
    target_results = {
        "high_credit_outstanding": {
            "label": "Customers with high credit limit and outstanding balance",
            "rows": [{"company_name": "Acme Corp", "credit_limit": 600000, "outstanding_balance": 1000}],
            "row_count": 1,
            "status": "success",
        },
        "fast_movers_low_stock": {
            "label": "Fast-moving items with low stock",
            "rows": [
                {
                    "product_id": 1,
                    "sku": "SKU-A",
                    "product_name": "Alpha Widget",
                    "units_sold": 500,
                    "warehouse_name": "North",
                    "available_stock": 100,
                    "reorder_level": 20,
                    "is_low_stock": False,
                },
                {
                    "product_id": 2,
                    "sku": "SKU-B",
                    "product_name": "Beta Gadget",
                    "units_sold": 300,
                    "warehouse_name": "South",
                    "available_stock": 50,
                    "reorder_level": 10,
                    "is_low_stock": False,
                },
                {
                    "product_id": 3,
                    "sku": "SKU-C",
                    "product_name": "Gamma Part",
                    "units_sold": 200,
                    "warehouse_name": "East",
                    "available_stock": 30,
                    "reorder_level": 5,
                    "is_low_stock": False,
                },
            ],
            "row_count": 3,
            "status": "success",
        },
    }
    text = build_multi_target_insight(CREDIT_STOCK_QUERY, target_results)
    assert "Summary:" in text
    assert "1 party" in text
    assert "Alpha Widget" in text
    assert "Beta Gadget" in text
    assert "Gamma Part" in text
    assert "units sold" in text.lower()
    assert "none of the top 3" in text.lower()
    assert "No matching records found" not in text


def test_credit_many_rows_headline():
    target_results = {
        "high_credit_outstanding": {
            "label": "Credit parties",
            "rows": [
                {"company_name": "A", "credit_limit": 600000, "outstanding_balance": 1},
                {"company_name": "B", "credit_limit": 700000, "outstanding_balance": 2},
            ],
            "row_count": 74,
            "status": "success",
        },
        "fast_movers_low_stock": {
            "label": "Low stock",
            "rows": [
                {
                    "product_id": 10,
                    "sku": "FAST-1",
                    "product_name": "Fast One",
                    "units_sold": 1000,
                    "warehouse_name": "Main",
                    "available_stock": 200,
                    "reorder_level": 50,
                    "is_low_stock": False,
                },
            ],
            "row_count": 1,
            "status": "success",
        },
    }
    text = try_multi_target_insight(
        "MULTI_STEP", CREDIT_STOCK_QUERY, target_results
    )
    assert text is not None
    assert "74 parties" in text
    assert "credit above 5 Lakhs" in text
    assert "outstanding balance" in text
    assert "Fast One" in text
