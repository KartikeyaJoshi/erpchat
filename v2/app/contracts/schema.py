"""Schema explorer API contracts."""

from typing import Any

from pydantic import BaseModel, Field


class SchemaColumn(BaseModel):
    name: str
    data_type: str = ""
    udt_name: str = ""
    is_nullable: bool = True
    is_primary_key: bool = False
    foreign_key: str | None = None


class SchemaTable(BaseModel):
    columns: list[SchemaColumn] = Field(default_factory=list)
    primary_key: str | None = None
    foreign_keys: dict[str, str] = Field(default_factory=dict)
    row_count: int = 0
    sample_rows: list[dict[str, Any]] = Field(default_factory=list)


class SchemaRelationship(BaseModel):
    from_table: str
    from_column: str
    to_table: str
    to_column: str


class SchemaExplorerResponse(BaseModel):
    fetched_at: str
    database: str = "public"
    table_count: int = 0
    tables: dict[str, SchemaTable] = Field(default_factory=dict)
    relationships: list[SchemaRelationship] = Field(default_factory=list)
    cached: bool = False
