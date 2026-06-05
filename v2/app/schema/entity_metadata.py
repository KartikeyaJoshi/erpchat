"""Entity metadata from governed schema for disambiguation and labels."""

from __future__ import annotations

from dataclasses import dataclass

from app.schema.loader import load_schema, table_primary_key


@dataclass(frozen=True)
class EntityMetadata:
    table: str
    primary_key: str
    noun: str
    label_columns: tuple[str, ...]
    lookup_columns: tuple[str, ...]
    measure_columns: tuple[str, ...]


def get_entity_metadata(table: str) -> EntityMetadata | None:
    """Return entity config for a table, or None if the table is not disambiguable."""
    schema = load_schema()
    meta = schema.get("tables", {}).get(table, {})
    entity = meta.get("entity")
    if not entity:
        return None

    pk = meta.get("primary_key") or table_primary_key(table)
    if not pk:
        return None

    noun = str(entity.get("noun") or table.replace("_", " ").rstrip("s"))
    label_columns = tuple(entity.get("label_columns") or ())
    lookup_columns = tuple(entity.get("lookup_columns") or label_columns)
    measure_columns = tuple(entity.get("measure_columns") or ())

    if not label_columns:
        # Fallback: non-PK string-like columns from schema (excluding measures)
        measure_set = {c.lower() for c in measure_columns}
        pk_l = pk.lower()
        label_columns = tuple(
            c
            for c in meta.get("columns", [])
            if c.lower() != pk_l and c.lower() not in measure_set
        )[:4]

    return EntityMetadata(
        table=table,
        primary_key=pk,
        noun=noun,
        label_columns=label_columns,
        lookup_columns=lookup_columns,
        measure_columns=measure_columns,
    )


def tables_with_entity_metadata() -> dict[str, EntityMetadata]:
    """All tables that declare an ``entity`` block in the governed schema."""
    out: dict[str, EntityMetadata] = {}
    for table in load_schema().get("tables", {}):
        entity = get_entity_metadata(table)
        if entity:
            out[table] = entity
    return out


def resolve_table_from_filter_key(filter_key: str) -> EntityMetadata | None:
    """Map a resolved_filters key (usually a PK column) back to entity metadata."""
    key = filter_key.strip().lower()
    for entity in tables_with_entity_metadata().values():
        if entity.primary_key.lower() == key:
            return entity
    return None
