"""LLM entity extraction contract for hybrid entity matching."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class EntityExtractionOutput(BaseModel):
    use_entity_match: bool = Field(
        default=False,
        description="True when query should use strict_word_similarity template.",
    )
    query_kind: Literal[
        "warehouse_stock",
        "sku_stock",
        "customer_lookup",
        "product_lookup",
        "none",
    ] = "none"
    parameter: str = ""
    table: str = ""
    column: str = ""
    phrase: str = ""
