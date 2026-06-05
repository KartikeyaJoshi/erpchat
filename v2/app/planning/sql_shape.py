"""Structural SQL analysis for ambiguous single-entity lookup detection."""

from __future__ import annotations

import re
from dataclasses import dataclass

import sqlglot
from sqlglot import exp

from app.schema.entity_metadata import EntityMetadata

_AGGREGATE_FUNCS = frozenset({"count", "sum", "avg", "min", "max", "stddev", "variance"})
_SCORE_COLUMNS = frozenset({"match_score", "similarity_score"})


@dataclass(frozen=True)
class SqlQueryShape:
    primary_table: str | None
    select_columns: tuple[str, ...]
    where_columns: tuple[str, ...]
    has_group_by: bool
    has_aggregates: bool


def _normalize_sql(sql: str) -> str:
    return sql.strip().rstrip(";")


def _column_name(node: exp.Expression) -> str | None:
    if isinstance(node, exp.Column):
        return (node.name or "").lower() or None
    if isinstance(node, exp.Alias) and node.this:
        if isinstance(node.this, exp.Column):
            return (node.this.name or "").lower() or None
        if isinstance(node.this, exp.AggFunc):
            return None
    return None


def _parse_tree(sql: str) -> exp.Expression | None:
    try:
        return sqlglot.parse_one(_normalize_sql(sql), dialect="postgres")
    except Exception:  # noqa: BLE001
        return None


def _infer_primary_table(tree: exp.Expression) -> str | None:
    counts: dict[str, int] = {}
    for table in tree.find_all(exp.Table):
        name = (table.name or "").lower()
        if name:
            counts[name] = counts.get(name, 0) + 1
    if not counts:
        return None
    return max(counts, key=counts.get)


def _resolve_table_for_column(
    col_table: str,
    alias_map: dict[str, str],
) -> str | None:
    ref = col_table.lower()
    if ref in alias_map:
        return alias_map[ref]
    return ref or None


def analyze_sql_shape(sql: str) -> SqlQueryShape | None:
    tree = _parse_tree(sql)
    if tree is None:
        return _analyze_sql_shape_regex(sql)

    alias_map: dict[str, str] = {}
    for table in tree.find_all(exp.Table):
        name = (table.name or "").lower()
        alias = (table.alias_or_name or "").lower()
        if name:
            alias_map[name] = name
            if alias and alias != name:
                alias_map[alias] = name

    select_columns: list[str] = []
    has_aggregates = False
    for select in tree.find_all(exp.Select):
        for expr in select.expressions:
            if isinstance(expr, exp.AggFunc) or (
                isinstance(expr, exp.Alias) and isinstance(expr.this, exp.AggFunc)
            ):
                has_aggregates = True
            col = _column_name(expr)
            if col:
                select_columns.append(col)
            elif isinstance(expr, exp.Alias) and expr.alias:
                select_columns.append(str(expr.alias).lower())
        break

    where_columns: list[str] = []
    for where in tree.find_all(exp.Where):
        for col in where.find_all(exp.Column):
            col_name = (col.name or "").lower()
            if col_name:
                where_columns.append(col_name)

    has_group_by = bool(list(tree.find_all(exp.Group)))
    primary = _infer_primary_table(tree)

    return SqlQueryShape(
        primary_table=primary,
        select_columns=tuple(dict.fromkeys(select_columns)),
        where_columns=tuple(dict.fromkeys(where_columns)),
        has_group_by=has_group_by,
        has_aggregates=has_aggregates,
    )


def _analyze_sql_shape_regex(sql: str) -> SqlQueryShape | None:
    """Fallback when sqlglot cannot parse the statement."""
    text = _normalize_sql(sql)
    from_match = re.search(
        r"\bfrom\s+(?:public\.)?(\w+)",
        text,
        re.IGNORECASE,
    )
    if not from_match:
        return None

    select_match = re.search(
        r"select\s+(distinct\s+)?(.+?)\s+from\b",
        text,
        re.IGNORECASE | re.DOTALL,
    )
    select_part = select_match.group(2) if select_match else ""
    select_columns = tuple(
        c.strip().split(".")[-1].lower()
        for c in select_part.split(",")
        if c.strip() and not re.match(r"^\w+\(", c.strip(), re.I)
    )

    where_match = re.search(r"\bwhere\b(.+?)(?:\bgroup\b|\border\b|\blimit\b|$)", text, re.I | re.S)
    where_columns: tuple[str, ...] = ()
    if where_match:
        where_columns = tuple(
            m.lower()
            for m in re.findall(r"(\w+)\s*=", where_match.group(1))
        )

    return SqlQueryShape(
        primary_table=from_match.group(1).lower(),
        select_columns=select_columns,
        where_columns=where_columns,
        has_group_by=bool(re.search(r"\bgroup\s+by\b", text, re.I)),
        has_aggregates=bool(re.search(r"\b(count|sum|avg|min|max)\s*\(", text, re.I)),
    )


def shape_filters_primary_key(shape: SqlQueryShape, entity: EntityMetadata) -> bool:
    pk = entity.primary_key.lower()
    return pk in {c.lower() for c in shape.where_columns}


def is_ambiguous_single_entity_lookup(
    shape: SqlQueryShape,
    entity: EntityMetadata,
    rows: list[dict],
) -> bool:
    """
    True when SQL shape + schema roles indicate a single-record answer was expected
    but multiple rows were returned.
    """
    if shape.has_group_by or shape.has_aggregates:
        return False

    if shape_filters_primary_key(shape, entity):
        return False

    if len(rows) <= 1:
        return False

    pk_l = entity.primary_key.lower()
    select = {c.lower() for c in shape.select_columns}
    measures = {c.lower() for c in entity.measure_columns}
    lookups = {c.lower() for c in entity.lookup_columns}
    where = {c.lower() for c in shape.where_columns}
    score_cols = _SCORE_COLUMNS

    # Scalar measure-only projection (e.g. SELECT salary … multiple rows)
    if select and select <= (measures | score_cols):
        return True

    # Name / natural-key lookup returned multiple rows
    if where & lookups:
        return True

    # PK projected but not unique per row
    if pk_l in select:
        return True

    # Small projection without intentional listing signals
    if len(select) <= 3 and not shape.has_group_by:
        return True

    # Fuzzy name match with attribute / label projection (e.g. is_discontinued lookup)
    if select & score_cols and (select & (lookups | measures | {pk_l})):
        return True

    return False


def uses_fuzzy_similarity_match(sql: str) -> bool:
    text = (sql or "").lower()
    return "strict_word_similarity" in text
