"""Heuristic multi-step decomposition tests."""

from app.planning.decomposition import (
    parse_credit_threshold,
    parse_sku,
    try_heuristic_multi_step,
)
from app.planning.orchestration import get_execution_targets, normalize_planner_output
from app.contracts.planner import PlannerOutput


CREDIT_SKU_QUERY = (
    "Which customers have credit limit of 2500000 and above. "
    "Also tell the stock level of SKU-1001-363 in the inventory."
)


def test_parse_credit_threshold_and_sku():
    assert parse_credit_threshold(CREDIT_SKU_QUERY) == 2_500_000
    assert parse_sku(CREDIT_SKU_QUERY) == "SKU-1001-363"


def test_parse_sku_ignores_duplicate_sku_prefix_in_intent():
    assert parse_sku("For SKU SKU-1001-363 by warehouse") == "SKU-1001-363"
    assert parse_sku("products.sku = 'SKU-1001-363'") == "SKU-1001-363"


def test_heuristic_multi_step_builds_two_targets():
    targets = try_heuristic_multi_step(CREDIT_SKU_QUERY)
    assert targets is not None
    assert len(targets) == 2
    assert targets[0].id == "high_credit_customers"
    assert targets[0].tables == ["customers"]
    assert targets[1].id == "sku_stock_by_warehouse"
    assert targets[1].tables == ["products", "inventory"]


def test_normalize_planner_upgrades_single_to_multi_step():
    plan = PlannerOutput(
        category="DIRECT_QUERY",
        query_mode="SINGLE",
        targets=[],
        steps=["Step 1: combined query"],
    )
    plan = normalize_planner_output(plan, CREDIT_SKU_QUERY)
    assert plan.query_mode == "MULTI_STEP"
    assert len(plan.targets) == 2
    targets = get_execution_targets(plan, CREDIT_SKU_QUERY)
    assert len(targets) == 2
    assert targets[0].tables == ["customers"]
