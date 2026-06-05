"""Parse natural-language record references into schema-correct filters."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from app.schema.column_filter import column_filter_kind
from app.schema.entity_metadata import EntityMetadata

MatchMode = Literal["exact", "similarity"]

_NUMERIC_ENTITY_RE = re.compile(
    r"\b("
    r"order|employee|customer|product|payslip|department|dept|"
    r"item|invoice|movement|inventory|account|party|client"
    r")\s*(?:no\.?|number|#)?\s*(\d+)\b",
    re.IGNORECASE,
)

_BARE_NUMERIC_RE = re.compile(r"^\s*#?\s*(\d+)\s*$")

_HASH_NUMERIC_RE = re.compile(r"#\s*(\d+)\b")


@dataclass(frozen=True)
class RecordFilter:
    column: str
    value: str
    match_mode: MatchMode
    value_is_numeric: bool = False


def extract_numeric_reference(phrase: str, *, noun: str | None = None) -> str | None:
    """Extract integer id from phrases like 'Order No 408', '408', 'employee 42'."""
    text = phrase.strip()
    if not text:
        return None

    bare = _BARE_NUMERIC_RE.match(text)
    if bare:
        return bare.group(1)

    hash_match = _HASH_NUMERIC_RE.search(text)
    if hash_match:
        return hash_match.group(1)

    if noun:
        noun_singular = noun.lower().strip().rstrip("s")
        noun_pattern = re.compile(
            rf"\b{re.escape(noun_singular)}s?\s*(?:no\.?|number|#)?\s*(\d+)\b",
            re.IGNORECASE,
        )
        match = noun_pattern.search(text)
        if match:
            return match.group(1)

    match = _NUMERIC_ENTITY_RE.search(text)
    if match:
        return match.group(2)

    trailing = re.search(r"\b(\d+)\s*$", text)
    if trailing and len(text.split()) <= 3:
        return trailing.group(1)

    return None


def resolve_record_filter(
    table: str,
    *,
    phrase: str,
    sku: str | None,
    entity: EntityMetadata | None,
) -> RecordFilter | None:
    """
    Map user phrase + schema entity metadata to the correct filter column,
    value, and match mode (exact vs fuzzy).
    """
    phrase = phrase.strip()
    if not phrase and not sku:
        return None
    lookup_columns = list(entity.lookup_columns) if entity else []
    pk = entity.primary_key if entity else None
    noun = entity.noun if entity else None

    if sku:
        for col in lookup_columns:
            if column_filter_kind(table, col) == "exact_code" and col.lower() == "sku":
                return RecordFilter(col, sku, "exact", False)
        if table == "products":
            return RecordFilter("sku", sku, "exact", False)

    ordered_cols: list[str] = []
    if pk:
        ordered_cols.append(pk)
    for col in lookup_columns:
        if col not in ordered_cols:
            ordered_cols.append(col)

    for col in ordered_cols:
        kind = column_filter_kind(table, col)
        if kind == "exact_numeric":
            num = extract_numeric_reference(phrase, noun=noun)
            if num is not None:
                return RecordFilter(col, num, "exact", True)

    if "@" in phrase:
        for col in ordered_cols:
            if col.lower() == "email":
                return RecordFilter(col, phrase, "exact", False)

    for col in ordered_cols:
        kind = column_filter_kind(table, col)
        if kind == "exact_code":
            if col.lower() == "sku":
                continue
            code = phrase.strip()
            if code:
                return RecordFilter(col, code, "exact", False)

    for col in ordered_cols:
        if column_filter_kind(table, col) == "fuzzy_text":
            return RecordFilter(col, phrase, "similarity", False)

    if entity and pk:
        kind = column_filter_kind(table, pk)
        if kind == "exact_text":
            return RecordFilter(pk, phrase, "exact", False)

    return None
