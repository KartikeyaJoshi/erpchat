"""LangGraph workflow with SQL validator gate and multi-step orchestration."""

from typing import Literal

from langgraph.graph import END, StateGraph

from app.config import MAX_SQL_RETRIES_PER_TARGET
from app.nodes import (
    database_executor_node,
    insight_synthesizer_node,
    planner_node,
    python_analyzer_node,
    sql_generator_node,
    sql_validator_node,
)
from app.planning.orchestration import has_more_targets, should_finalize_partial
from app.state import AnalystState


def validator_routing_edge(
    state: AnalystState,
) -> Literal["sql_generator", "database_executor", "python_analyzer", "__end__"]:
    if state.get("validation_error"):
        if state.get("retry_count", 0) <= MAX_SQL_RETRIES_PER_TARGET:
            return "sql_generator"
        if should_finalize_partial(state):
            return "python_analyzer"
        return "__end__"
    return "database_executor"


def orchestration_routing_edge(
    state: AnalystState,
) -> Literal["sql_generator", "python_analyzer", "__end__"]:
    if state.get("sql_error"):
        if state.get("retry_count", 0) <= MAX_SQL_RETRIES_PER_TARGET:
            return "sql_generator"
        if should_finalize_partial(state):
            return "python_analyzer"
        return "__end__"
    if has_more_targets(state):
        return "sql_generator"
    return "python_analyzer"


workflow_builder = StateGraph(AnalystState)

workflow_builder.add_node("planner", planner_node)
workflow_builder.add_node("sql_generator", sql_generator_node)
workflow_builder.add_node("sql_validator", sql_validator_node)
workflow_builder.add_node("database_executor", database_executor_node)
workflow_builder.add_node("python_analyzer", python_analyzer_node)
workflow_builder.add_node("insight_synthesizer", insight_synthesizer_node)

def planner_routing_edge(
    state: AnalystState,
) -> Literal["sql_generator", "insight_synthesizer"]:
    if state.get("out_of_scope"):
        return "insight_synthesizer"
    return "sql_generator"


workflow_builder.set_entry_point("planner")
workflow_builder.add_conditional_edges(
    "planner",
    planner_routing_edge,
    {
        "sql_generator": "sql_generator",
        "insight_synthesizer": "insight_synthesizer",
    },
)
workflow_builder.add_edge("sql_generator", "sql_validator")

workflow_builder.add_conditional_edges(
    "sql_validator",
    validator_routing_edge,
    {
        "sql_generator": "sql_generator",
        "database_executor": "database_executor",
        "python_analyzer": "python_analyzer",
        "__end__": END,
    },
)

workflow_builder.add_conditional_edges(
    "database_executor",
    orchestration_routing_edge,
    {
        "sql_generator": "sql_generator",
        "python_analyzer": "python_analyzer",
        "__end__": END,
    },
)

workflow_builder.add_edge("python_analyzer", "insight_synthesizer")
workflow_builder.add_edge("insight_synthesizer", END)

compiled_analyst_graph = workflow_builder.compile()
