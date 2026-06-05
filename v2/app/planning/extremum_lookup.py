"""Schema-driven SQL for single-record highest/lowest (extremum) questions."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from app.config import SQL_ROW_LIMIT
from app.planning.decomposition import parse_rank_limit
from app.schema.entity_metadata import get_entity_metadata, tables_with_entity_metadata
from app.schema.loader import load_schema, table_primary_key
from app.schema.scope_vocabulary import _COLUMN_ALIASES

SortDirection = Literal["ASC", "DESC"]

_EXTREMUM_WORDS_RE = re.compile(
    r"\b(highest|lowest|maximum|minimum|max|min|most|least|best|worst)\b",
    re.IGNORECASE,
)

_WHICH_WHAT_RE = re.compile(r"\b(which|what)\b", re.IGNORECASE)

_MEASURE_AFTER_EXTREMUM_RE = re.compile(
    r"\b(?:has\s+(?:the\s+)?)?"
    r"(?:highest|lowest|maximum|minimum|max|min|most|least|best|worst)\s+"
    r"(\w+(?:\s+\w+)?)",
    re.IGNORECASE,
)

_ENTITY_NOUN_RE = re.compile(
    r"\b(?:which|what)\s+(\w+)\s+has\b",
    re.IGNORECASE,
)

_YEAR_IN_QUERY_RE = re.compile(r"\b(20\d{2})\b")


@dataclass(frozen=True)
class ExtremumIntent:
    table: str
    measure_column: str
    id_column: str
    direction: SortDirection
    filter_year: int | None = None
    date_column: str | None = None


def query_is_single_extremum(user_query: str) -> bool:
    """True for 'which order has least tax amount' — not top-N product rankings."""
    text = user_query.strip()
    if not text:
        return False
    if not _WHICH_WHAT_RE.search(text):
        return False
    if not _EXTREMUM_WORDS_RE.search(text):
        return False
    top_n = parse_rank_limit(text)
    if top_n is not None and top_n > 1:
        return False
    if re.search(r"\btop\s+\d+\b", text, re.IGNORECASE) and top_n and top_n > 1:
        return False
    return parse_extremum_intent(text) is not None


def _extremum_sort_direction(user_query: str) -> SortDirection:
    q = user_query.lower()
    if re.search(r"\b(highest|maximum|max|most|best)\b", q):
        return "DESC"
    if re.search(r"\b(lowest|minimum|min|least|worst|bottom)\b", q):
        return "ASC"
    return "DESC"


def _extract_measure_phrase(user_query: str) -> str | None:
    match = _MEASURE_AFTER_EXTREMUM_RE.search(user_query)
    if not match:
        return None
    phrase = match.group(1).lower().strip()
    stop = ("in", "for", "during", "from", "at", "on", "with")
    words = phrase.split()
    while words and words[-1] in stop:
        words.pop()
    return " ".join(words) if words else None


def _resolve_column_on_table(phrase: str, table: str, columns: list[str]) -> str | None:
    phrase_key = phrase.lower().strip().replace(" ", "_")
    col_map = {c.lower(): c for c in columns}
    if phrase_key in col_map:
        return col_map[phrase_key]
    for col in columns:
        col_l = col.lower()
        if phrase_key == col_l or phrase.replace("_", " ") == col_l.replace("_", " "):
            return col
        for alias in _COLUMN_ALIASES.get(col_l, ()):
            if phrase.lower() == alias or phrase_key == alias.replace(" ", "_"):
                return col
    return None


def _table_for_entity_noun(noun: str) -> str | None:
    target = noun.lower().strip().rstrip("s")
    for table, entity in tables_with_entity_metadata().items():
        enoun = entity.noun.lower().strip().rstrip("s")
        if target == enoun or target in enoun or enoun in target:
            return table
        if table.replace("_", " ").startswith(target):
            return table
    return None


def _infer_entity_noun(user_query: str) -> str | None:
    match = _ENTITY_NOUN_RE.search(user_query)
    if match:
        return match.group(1).lower()
    q = user_query.lower()
    for table, entity in tables_with_entity_metadata().items():
        noun = entity.noun.lower()
        if re.search(rf"\b{re.escape(noun)}s?\b", q):
            return noun
    return None


def _resolve_measure(user_query: str) -> tuple[str, str] | None:
    phrase = _extract_measure_phrase(user_query)
    if not phrase:
        return None

    noun = _infer_entity_noun(user_query)
    preferred_table = _table_for_entity_noun(noun) if noun else None

    schema = load_schema()
    candidates: list[tuple[str, str]] = []

    for table, meta in schema.get("tables", {}).items():
        columns = list(meta.get("columns") or [])
        entity = meta.get("entity") or {}
        for key in ("measure_columns", "label_columns", "lookup_columns"):
            for col in entity.get(key) or ():
                if col not in columns:
                    columns.append(col)

        resolved = _resolve_column_on_table(phrase, table, columns)
        if resolved:
            candidates.append((table, resolved))

    if not candidates:
        return None

    if preferred_table:
        for table, col in candidates:
            if table == preferred_table:
                return table, col

    if len(candidates) == 1:
        return candidates[0]

    # Prefer entity table whose PK/id column matches query noun (e.g. order + tax_amount)
    if preferred_table:
        return candidates[0]

    return candidates[0]


def parse_extremum_intent(
    user_query: str,
    *,
    default_year: int | None = None,
) -> ExtremumIntent | None:
    text = user_query.strip()
    if not text or not _WHICH_WHAT_RE.search(text) or not _EXTREMUM_WORDS_RE.search(text):
        return None

    resolved = _resolve_measure(text)
    if not resolved:
        return None

    table, measure_column = resolved
    entity = get_entity_metadata(table)
    pk = table_primary_key(table) or (entity.primary_key if entity else None)
    if not pk:
        return None

    year_match = _YEAR_IN_QUERY_RE.search(text)
    filter_year: int | None = None
    date_column: str | None = None
    if year_match:
        filter_year = int(year_match.group(1))
    elif re.search(r"\b(this|current)\s+year\b", text, re.IGNORECASE) and default_year:
        filter_year = default_year

    meta = load_schema().get("tables", {}).get(table, {})
    cols = meta.get("columns") or []
    if "order_date" in cols:
        date_column = "order_date"
    elif "entry_date" in cols:
        date_column = "entry_date"

    return ExtremumIntent(
        table=table,
        measure_column=measure_column,
        id_column=pk,
        direction=_extremum_sort_direction(text),
        filter_year=filter_year,
        date_column=date_column if filter_year else None,
    )


def build_extremum_sql(intent: ExtremumIntent, *, row_limit: int = 1) -> str:
    id_col = intent.id_column
    measure = intent.measure_column
    table = intent.table
    order = intent.direction

    where_parts: list[str] = []
    if intent.filter_year and intent.date_column:
        year = intent.filter_year
        where_parts.append(
            f"{intent.date_column} >= '{year}-01-01' "
            f"AND {intent.date_column} < '{year + 1}-01-01'"
        )

    where_sql = f" WHERE {' AND '.join(where_parts)}" if where_parts else ""
    limit = row_limit if row_limit > 0 else 1

    return (
        f"SELECT {id_col}, {measure} FROM public.{table}{where_sql} "
        f"ORDER BY {measure} {order} LIMIT {limit}"
    )


def try_extremum_template_sql(
    user_query: str,
    *,
    year: int,
    row_limit: int | None = None,
) -> str | None:
    intent = parse_extremum_intent(user_query, default_year=year)
    if intent is None:
        return None
    limit = row_limit if row_limit is not None else 1
    return build_extremum_sql(intent, row_limit=limit)
