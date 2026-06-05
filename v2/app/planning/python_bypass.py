"""Decide when SQL rows already answer the question — skip LLM Python."""

from __future__ import annotations

import re

_EXTREMUM_QUERY_RE = re.compile(
    r"\b("
    r"highest|lowest|maximum|minimum|max|min|most|least|"
    r"best|worst|top\s+1|bottom\s+1"
    r")\b",
    re.IGNORECASE,
)

_WHICH_WHAT_RE = re.compile(r"\b(which|what)\b", re.IGNORECASE)

_AGGREGATE_SQL_RE = re.compile(
    r"\b(count|sum|avg|min|max)\s*\(",
    re.IGNORECASE,
)


def should_bypass_python_analyzer(
    user_query: str,
    rows: list[dict],
    *,
    sql: str = "",
    query_mode: str = "SINGLE",
    execution_category: str = "",
) -> bool:
    """
    True when database rows (from successful SQL) fully answer the question
    and running LLM-generated Python adds no value.
    """
    if query_mode == "MULTI_STEP":
        return False

    if execution_category == "DIRECT_QUERY":
        return True

    text = user_query.strip()
    if not text:
        return False

    q = text.lower()
    sql_l = (sql or "").lower()
    row_count = len(rows)

    if row_count == 0:
        return True

    if _EXTREMUM_QUERY_RE.search(q) and row_count <= 5:
        return True

    if _WHICH_WHAT_RE.search(q) and row_count == 1:
        return True

    if row_count == 1 and _AGGREGATE_SQL_RE.search(sql_l):
        return True

    if row_count == 1 and re.search(r"\blimit\s+1\b", sql_l):
        return True

    return False
