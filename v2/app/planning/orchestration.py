"""Multi-step orchestration helpers."""

from __future__ import annotations

from app.config import MAX_TARGETS, MULTI_STEP_ENABLED
from app.contracts.planner import PlannerOutput
from app.contracts.targets import QueryTarget
from app.planning.decomposition import try_heuristic_multi_step
from app.schema.loader import allowed_tables


def canonical_table_name(table: str) -> str:
    """Map planner/SQL table refs to schema keys (strip public. prefix)."""
    name = table.strip().lower()
    if name.startswith("public."):
        name = name[len("public.") :]
    return name


def normalize_target_tables(targets: list[QueryTarget]) -> list[QueryTarget]:
    """
    Validate and rewrite target.tables to bare schema names (customers, not public.customers).
    """
    allowed = allowed_tables()
    normalized: list[QueryTarget] = []
    for target in targets:
        canon_tables: list[str] = []
        for table in target.tables:
            canon = canonical_table_name(table)
            if canon not in allowed:
                raise ValueError(
                    f"Target '{target.id}' references unknown table: {table}"
                )
            canon_tables.append(canon)
        normalized.append(target.model_copy(update={"tables": canon_tables}))
    return normalized


def normalize_planner_output(parsed: PlannerOutput, user_query: str) -> PlannerOutput:
    """Ensure query_mode and targets are consistent."""
    if parsed.category == "OUT_OF_SCOPE":
        parsed.query_mode = "SINGLE"
        parsed.targets = []
        return parsed

    if not MULTI_STEP_ENABLED:
        parsed.query_mode = "SINGLE"
        parsed.targets = []
        return parsed

    if parsed.query_mode == "MULTI_STEP" and len(parsed.targets) >= 2:
        parsed.targets = normalize_target_tables(parsed.targets[:MAX_TARGETS])
        return parsed

    heuristic_targets = try_heuristic_multi_step(user_query)
    if heuristic_targets and len(heuristic_targets) >= 2:
        parsed.query_mode = "MULTI_STEP"
        parsed.targets = normalize_target_tables(heuristic_targets[:MAX_TARGETS])
        if not parsed.steps or len(parsed.steps) < 2:
            parsed.steps = [
                f"Step 1: Query customers table for credit_limit >= threshold ({user_query[:80]}).",
                f"Step 2: Query products and inventory for SKU stock by warehouse ({user_query[:80]}).",
            ]
        return parsed

    parsed.query_mode = "SINGLE"
    parsed.targets = []
    return parsed


def get_execution_targets(parsed: PlannerOutput, user_query: str) -> list[QueryTarget]:
    """Return the list of targets to execute (one synthetic target for SINGLE mode)."""
    if parsed.query_mode == "MULTI_STEP" and len(parsed.targets) >= 2:
        return parsed.targets
    return [
        QueryTarget(
            id="primary",
            label=user_query.strip(),
            tables=[],
            intent=user_query.strip(),
        )
    ]


def targets_to_state_dicts(targets: list[QueryTarget]) -> list[dict]:
    return [t.model_dump() for t in targets]


def current_target_from_state(state: dict) -> QueryTarget | None:
    targets = state.get("targets") or []
    idx = state.get("current_target_index", 0)
    if not targets or idx >= len(targets):
        return None
    raw = targets[idx]
    if isinstance(raw, QueryTarget):
        return raw
    return QueryTarget.model_validate(raw)


def has_more_targets(state: dict) -> bool:
    targets = state.get("targets") or []
    idx = state.get("current_target_index", 0)
    return idx < len(targets)


def total_row_count(target_results: dict) -> int:
    return sum(
        int(bundle.get("row_count", 0))
        for bundle in target_results.values()
        if isinstance(bundle, dict)
    )


def should_finalize_partial(state: dict) -> bool:
    """Continue to insight when at least one target succeeded but pipeline hit errors."""
    target_results = state.get("target_results") or {}
    if not target_results:
        return False
    return any(
        isinstance(bundle, dict) and bundle.get("status") == "success"
        for bundle in target_results.values()
    )
