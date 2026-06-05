"""Multi-step orchestration unit tests."""

from app.contracts.planner import PlannerOutput
from app.contracts.targets import QueryTarget
from app.insights.grounding import build_multi_target_insight, try_multi_target_insight
from app.planning.orchestration import (
    canonical_table_name,
    get_execution_targets,
    has_more_targets,
    normalize_planner_output,
    normalize_target_tables,
    should_finalize_partial,
    total_row_count,
)


def test_single_mode_wraps_primary_target():
    plan = PlannerOutput(
        category="DIRECT_QUERY",
        query_mode="SINGLE",
        targets=[],
        steps=["Step 1: fetch data"],
    )
    plan = normalize_planner_output(plan, "What is revenue?")
    targets = get_execution_targets(plan, "What is revenue?")
    assert len(targets) == 1
    assert targets[0].id == "primary"


def test_canonical_table_name_strips_public_prefix():
    assert canonical_table_name("public.customers") == "customers"
    assert canonical_table_name("PUBLIC.PRODUCTS") == "products"
    assert canonical_table_name("inventory") == "inventory"


def test_normalize_target_tables_accepts_public_prefix():
    targets = [
        QueryTarget(
            id="high_credit_customers",
            label="High credit customers",
            tables=["public.customers"],
            intent="credit_limit >= 2500000",
        ),
        QueryTarget(
            id="sku_stock",
            label="SKU stock",
            tables=["public.products", "public.inventory"],
            intent="stock for SKU-1001-363",
        ),
    ]
    normalized = normalize_target_tables(targets)
    assert normalized[0].tables == ["customers"]
    assert normalized[1].tables == ["products", "inventory"]


def test_multi_step_keeps_targets():
    plan = PlannerOutput(
        category="COMPLEX_ANALYSIS",
        query_mode="MULTI_STEP",
        targets=[
            QueryTarget(
                id="credit_parties",
                label="High credit with balance",
                tables=["customers"],
                intent="credit_limit > 500000 AND outstanding_balance > 0",
            ),
            QueryTarget(
                id="low_stock",
                label="Fast movers low stock",
                tables=["order_items", "sales_orders", "products", "inventory"],
                intent="Top 3 products by quantity; low stock by warehouse",
            ),
        ],
        steps=["Step 1", "Step 2"],
    )
    plan = normalize_planner_output(plan, "credit and stock")
    targets = get_execution_targets(plan, "credit and stock")
    assert len(targets) == 2


def test_multi_step_normalizes_public_prefix_from_planner():
    plan = PlannerOutput(
        category="COMPLEX_ANALYSIS",
        query_mode="MULTI_STEP",
        targets=[
            QueryTarget(
                id="high_credit_customers",
                label="High credit",
                tables=["public.customers"],
                intent="credit_limit >= 2500000",
            ),
            QueryTarget(
                id="sku_stock",
                label="SKU stock",
                tables=["public.products", "public.inventory"],
                intent="SKU-1001-363 stock by warehouse",
            ),
        ],
        steps=["Step 1", "Step 2"],
    )
    plan = normalize_planner_output(
        plan,
        "Which customers have credit limit of 2500000 and above. "
        "Also tell the stock level of SKU-1001-363.",
    )
    assert plan.query_mode == "MULTI_STEP"
    assert plan.targets[0].tables == ["customers"]
    assert plan.targets[1].tables == ["products", "inventory"]
    assert plan.targets[0].id == "high_credit_customers"
    assert plan.targets[1].id == "sku_stock"


def test_has_more_targets_advances():
    state = {
        "targets": [{"id": "a"}, {"id": "b"}],
        "current_target_index": 0,
    }
    assert has_more_targets(state) is True
    state["current_target_index"] = 1
    assert has_more_targets(state) is True
    state["current_target_index"] = 2
    assert has_more_targets(state) is False


def test_total_row_count_sums_targets():
    results = {
        "a": {"row_count": 4},
        "b": {"row_count": 10},
    }
    assert total_row_count(results) == 14


def test_should_finalize_partial_when_one_success():
    state = {
        "target_results": {
            "a": {"status": "success", "row_count": 1},
            "b": {"status": "failed", "error": "validation"},
        }
    }
    assert should_finalize_partial(state) is True


def test_multi_target_insight_includes_missing_planned_target():
    planned = [
        {"id": "credit_parties", "label": "Credit parties"},
        {"id": "low_stock", "label": "Low stock"},
    ]
    target_results = {
        "credit_parties": {
            "label": "Credit parties",
            "rows": [{"company_name": "Acme", "outstanding_balance": 100}],
            "row_count": 1,
            "status": "success",
        },
    }
    text = try_multi_target_insight("MULTI_STEP", "credit and stock", target_results, planned)
    assert text is not None
    assert "Credit parties" in text
    assert "Low stock" in text
    assert "not completed" in text.lower()


def test_multi_target_insight_sections():
    target_results = {
        "credit_parties": {
            "label": "Credit parties",
            "rows": [
                {
                    "company_name": "Acme",
                    "credit_limit": 600000,
                    "outstanding_balance": 1000,
                }
            ],
            "row_count": 1,
            "status": "success",
        },
        "low_stock": {
            "label": "Low stock items",
            "rows": [],
            "row_count": 0,
            "status": "success",
        },
    }
    text = try_multi_target_insight("MULTI_STEP", "credit and stock", target_results)
    assert text is not None
    assert "Credit parties" in text
    assert "no inventory rows" in text.lower() or "could not be listed" in text.lower()
