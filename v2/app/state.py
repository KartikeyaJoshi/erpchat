"""Central LangGraph state contract (Phase 1 + multi-step)."""

from typing import Any, TypedDict


class AnalystState(TypedDict, total=False):
    # Request context
    user_query: str
    current_year: int
    trace_id: str
    deterministic_mode: bool
    resolved_filters: dict[str, str]
    needs_clarification: bool
    clarification: dict[str, Any]
    # Fuzzy match / disambiguation (strict_word_similarity)
    entity_match_notes: list[str]

    entity_filter_parameter: str
    entity_filter_phrase: str
    entity_filter_value_column: str

    # Planning
    out_of_scope: bool
    execution_category: str
    logical_plan: list[str]
    query_mode: str  # SINGLE | MULTI_STEP
    targets: list[dict[str, Any]]
    current_target_index: int
    target_results: dict[str, dict[str, Any]]

    # SQL pipeline (current target)
    generated_sql: str
    sql_error: str
    validation_error: str
    validation_result: dict[str, Any]
    retry_count: int
    database_results: list[dict[str, Any]]

    # Python analysis
    python_code: str
    python_output: dict[str, Any]

    # Output
    final_insight: str
    error_code: str

    # Partial multi-step completion
    pipeline_partial: bool

    # Observability
    node_timings: dict[str, float]
    prompt_versions: dict[str, str]
    usage: dict[str, int]
    usage_steps: dict[str, dict[str, int]]
