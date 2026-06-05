"""Multi-step insight: credit + SKU (no cross-target message bleed)."""

from app.insights.grounding import build_multi_target_insight

CREDIT_SKU_QUERY = (
    "Which customers have credit limit of 2500000 and above. "
    "Also tell the stock level of SKU-1001-363 in the inventory."
)


def test_credit_sku_insight_no_repetition_or_wrong_section():
    target_results = {
        "high_credit_customers": {
            "label": "Customers with credit limit of 2500000 and above",
            "rows": [
                {
                    "company_name": "Acme Ltd",
                    "credit_limit": 3_000_000,
                    "outstanding_balance": 0,
                    "contact_name": "Raj",
                }
            ],
            "row_count": 247,
            "status": "success",
        },
        "sku_stock_by_warehouse": {
            "label": "Stock level of SKU-1001-363 in inventory",
            "rows": [],
            "row_count": 0,
            "status": "success",
        },
    }
    planned = [
        {"id": "high_credit_customers", "label": target_results["high_credit_customers"]["label"]},
        {"id": "sku_stock_by_warehouse", "label": target_results["sku_stock_by_warehouse"]["label"]},
    ]
    text = build_multi_target_insight(CREDIT_SKU_QUERY, target_results, planned_targets=planned)

    assert "Summary:" in text
    assert "247 customers have credit limit >= 2500000" in text
    assert "No warehouse stock found for SKU-1001-363" in text

    # No repeated count headline under section 1
    assert text.count("247 customers have a credit limit of 2500000") == 0
    assert text.count("247 customers have credit limit >= 2500000") == 1

    # SKU section must not use outstanding-balance copy
    assert "5 Lakhs" not in text.split("2. Stock level")[1]
    assert "outstanding balance" not in text.lower().split("2. stock level")[1]

    assert "Acme Ltd" in text


def test_credit_sku_insight_lists_warehouse_stock():
    target_results = {
        "high_credit_customers": {
            "label": "High credit",
            "rows": [],
            "row_count": 0,
            "status": "success",
        },
        "sku_stock_by_warehouse": {
            "label": "Stock for SKU-1001-363",
            "rows": [
                {
                    "sku": "SKU-1001-363",
                    "product_name": "Widget",
                    "warehouse_name": "North DC",
                    "stock_on_hand": 100,
                    "available_stock": 80,
                    "reorder_level": 20,
                }
            ],
            "row_count": 1,
            "status": "success",
        },
    }
    text = build_multi_target_insight(CREDIT_SKU_QUERY, target_results)
    assert "North DC" in text
    assert "on hand 100.00" in text
    assert "SKU-1001-363 has stock data" in text
