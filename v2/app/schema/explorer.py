"""Live Supabase schema + sample row explorer for the frontend."""

from __future__ import annotations

import re
import time
from typing import Any

from app.database import supabase_client

_TABLE_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_SAMPLE_ROW_LIMIT = 8
_SCHEMA = "public"

_server_cache: dict[str, Any] | None = None
_server_cache_at: float = 0.0
_SERVER_CACHE_TTL_SEC = 300


def _run_sql(query_text: str) -> list[dict[str, Any]]:
    response = supabase_client.rpc(
        "execute_raw_sql",
        {"query_text": query_text},
    ).execute()
    rows = response.data or []
    return [row for row in rows if isinstance(row, dict)]


def _safe_table_name(name: str) -> str:
    if not _TABLE_NAME_RE.match(name):
        raise ValueError(f"Invalid table name: {name}")
    return name


def _fetch_tables() -> list[str]:
    rows = _run_sql(
        f"""
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = '{_SCHEMA}'
          AND table_type = 'BASE TABLE'
        ORDER BY table_name
        """
    )
    return [
        str(row.get("table_name", "")).strip()
        for row in rows
        if row.get("table_name")
    ]


def _fetch_columns() -> dict[str, list[dict[str, Any]]]:
    rows = _run_sql(
        f"""
        SELECT
          table_name,
          column_name,
          data_type,
          udt_name,
          is_nullable,
          ordinal_position
        FROM information_schema.columns
        WHERE table_schema = '{_SCHEMA}'
        ORDER BY table_name, ordinal_position
        """
    )
    by_table: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        table = str(row.get("table_name", "")).strip()
        if not table:
            continue
        by_table.setdefault(table, []).append(
            {
                "name": str(row.get("column_name", "")),
                "data_type": str(row.get("data_type", "")),
                "udt_name": str(row.get("udt_name", "")),
                "is_nullable": str(row.get("is_nullable", "YES")).upper() == "YES",
            }
        )
    return by_table


def _fetch_primary_keys() -> dict[str, str]:
    rows = _run_sql(
        f"""
        SELECT tc.table_name, kcu.column_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name = kcu.constraint_name
         AND tc.table_schema = kcu.table_schema
        WHERE tc.table_schema = '{_SCHEMA}'
          AND tc.constraint_type = 'PRIMARY KEY'
        """
    )
    return {
        str(row["table_name"]): str(row["column_name"])
        for row in rows
        if row.get("table_name") and row.get("column_name")
    }


def _fetch_foreign_keys() -> tuple[dict[str, dict[str, str]], list[dict[str, str]]]:
    rows = _run_sql(
        f"""
        SELECT
          tc.table_name,
          kcu.column_name,
          ccu.table_name AS foreign_table_name,
          ccu.column_name AS foreign_column_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name = kcu.constraint_name
         AND tc.table_schema = kcu.table_schema
        JOIN information_schema.constraint_column_usage ccu
          ON ccu.constraint_name = tc.constraint_name
         AND ccu.table_schema = tc.table_schema
        WHERE tc.constraint_type = 'FOREIGN KEY'
          AND tc.table_schema = '{_SCHEMA}'
        """
    )
    by_table: dict[str, dict[str, str]] = {}
    relationships: list[dict[str, str]] = []
    for row in rows:
        table = str(row.get("table_name", ""))
        column = str(row.get("column_name", ""))
        foreign_table = str(row.get("foreign_table_name", ""))
        foreign_column = str(row.get("foreign_column_name", ""))
        if not all([table, column, foreign_table, foreign_column]):
            continue
        by_table.setdefault(table, {})[column] = f"{foreign_table}.{foreign_column}"
        relationships.append(
            {
                "from_table": table,
                "from_column": column,
                "to_table": foreign_table,
                "to_column": foreign_column,
            }
        )
    return by_table, relationships


def _fetch_row_counts(tables: list[str]) -> dict[str, int]:
    if not tables:
        return {}
    parts = []
    for table in tables:
        safe = _safe_table_name(table)
        parts.append(
            f"SELECT '{safe}' AS table_name, COUNT(*)::bigint AS row_count "
            f'FROM "{_SCHEMA}"."{safe}"'
        )
    rows = _run_sql(" UNION ALL ".join(parts))
    return {
        str(row.get("table_name", "")): int(row.get("row_count") or 0)
        for row in rows
        if row.get("table_name") is not None
    }


def fetch_table_preview(table_name: str) -> list[dict[str, Any]]:
    safe = _safe_table_name(table_name)
    return _run_sql(
        f'SELECT * FROM "{_SCHEMA}"."{safe}" LIMIT {_SAMPLE_ROW_LIMIT}'
    )


def fetch_live_schema(*, force_refresh: bool = False) -> dict[str, Any]:
    """Return tables, columns, relationships, and row counts (no sample rows)."""
    global _server_cache, _server_cache_at

    if (
        not force_refresh
        and _server_cache is not None
        and (time.time() - _server_cache_at) < _SERVER_CACHE_TTL_SEC
    ):
        return _server_cache

    tables = _fetch_tables()
    columns_by_table = _fetch_columns()
    primary_keys = _fetch_primary_keys()
    foreign_keys_by_table, relationships = _fetch_foreign_keys()
    row_counts = _fetch_row_counts(tables)

    table_payload: dict[str, Any] = {}
    for table_name in tables:
        cols = columns_by_table.get(table_name, [])
        pk = primary_keys.get(table_name)
        fks = foreign_keys_by_table.get(table_name, {})
        for col in cols:
            col["is_primary_key"] = col["name"] == pk
            col["foreign_key"] = fks.get(col["name"])

        table_payload[table_name] = {
            "columns": cols,
            "primary_key": pk,
            "foreign_keys": fks,
            "row_count": row_counts.get(table_name, 0),
            "sample_rows": [],
        }

    payload = {
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "database": _SCHEMA,
        "table_count": len(tables),
        "tables": table_payload,
        "relationships": relationships,
    }

    _server_cache = payload
    _server_cache_at = time.time()
    return payload
