"""Strip internal scoring fields from rows shown to insight LLM."""

from __future__ import annotations

from typing import Any

_INTERNAL_ROW_KEYS = frozenset(
    {
        "match_score",
        "similarity_score",
    }
)


def sanitize_rows_for_insight(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            out.append(row)
            continue
        cleaned = {
            k: v
            for k, v in row.items()
            if str(k).lower() not in _INTERNAL_ROW_KEYS
            and not str(k).lower().endswith("_match_score")
        }
        out.append(cleaned)
    return out
