"""Detect queries outside ERP business analytics scope."""

from __future__ import annotations

import json
import re

from app.schema.scope_vocabulary import (
    looks_like_entity_record_lookup,
    query_has_sku_reference,
    query_matches_scope_vocabulary,
)

OUT_OF_SCOPE_USER_MESSAGE = (
    "Please ask only business-related questions about this ERP data "
    "(for example customers, products, orders, inventory, revenue, credit, or stock)."
)

_ERP_TOPIC_RE = re.compile(
    r"\b("
    r"customer|customers|product|products|order|orders|revenue|sales|inventory|"
    r"warehouse|warehouses|credit|sku|invoice|invoiced|stock|party|parties|"
    r"lakhs?|lakh|erp|margin|profit|ledger|outstanding|discount|shipment|"
    r"units?\s+sold|fast[\s-]?moving|supplier|vendor|subtotal|tax|payment|"
    r"employee|employees|salary|payroll|department|departments|job\s+title|"
    r"manager|managers|hire\s+date|hr|human\s+resource"
    r")\b",
    re.IGNORECASE,
)

_ANALYTICS_INTENT_RE = re.compile(
    r"\b("
    r"how\s+many|how\s+much|top\s+\d+|list\b|show\b|calculate|compare|total\b|"
    r"count\b|sum\b|average|avg\b|between\b|growth|trend|rank|highest|lowest|"
    r"above\b|below\b|per\s+"
    r")\b",
    re.IGNORECASE,
)

_GENERAL_KNOWLEDGE_RE = re.compile(
    r"^\s*(what|who|when|where|define|explain)\s+(is|are|was|were)\s+",
    re.IGNORECASE,
)

_PLANNER_PROSE_MARKERS = (
    "i'm not able",
    "i am not able",
    "cannot help",
    "can't help",
    "outside my",
    "not a business",
    "general knowledge",
    "as an ai",
    "i cannot answer",
)


def _has_erp_signals(text: str) -> bool:
    return bool(
        _ERP_TOPIC_RE.search(text)
        or _ANALYTICS_INTENT_RE.search(text)
        or query_has_sku_reference(text)
        or query_matches_scope_vocabulary(text)
    )


def is_likely_in_scope(user_query: str) -> bool:
    """
    Fast heuristic: True when the question plausibly targets ERP analytics.
    False for general knowledge (e.g. 'What is Google?').
    """
    text = user_query.strip()
    if not text:
        return False

    if _has_erp_signals(text):
        return True

    if _GENERAL_KNOWLEDGE_RE.match(text):
        if looks_like_entity_record_lookup(text):
            return True
        return False

    # Short non-analytic questions without ERP vocabulary
    if len(text.split()) <= 8 and not _has_erp_signals(text):
        lowered = text.lower()
        if lowered.startswith(("hi", "hello", "hey", "thanks", "thank you")):
            return False

    return True


def is_planner_prose_refusal(raw: str) -> bool:
    """True when the planner returned plain text instead of JSON."""
    stripped = raw.strip()
    if not stripped:
        return True
    if stripped.startswith("{"):
        try:
            json.loads(stripped)
            return False
        except json.JSONDecodeError:
            pass
    lowered = stripped.lower()
    return any(marker in lowered for marker in _PLANNER_PROSE_MARKERS)


def is_planner_parse_failure_out_of_scope(raw: str, user_query: str) -> bool:
    """Treat prose planner output or off-topic queries as out-of-scope."""
    if is_planner_prose_refusal(raw):
        return True
    if not is_likely_in_scope(user_query):
        return True
    return False
