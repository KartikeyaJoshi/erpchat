"""Evidence-grounded insights for scalar SQL aggregates and multi-step reports."""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Any

from app.planning.decomposition import (
    parse_credit_threshold,
    parse_rank_limit,
    parse_sku,
)


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.replace(",", "").strip())
        except ValueError:
            return None
    return None


def _format_number(value: Any) -> str:
    parsed = _to_float(value)
    if parsed is not None:
        return f"{parsed:.2f}"
    return str(value)


def extract_verified_facts(rows: list[dict[str, Any]]) -> dict[str, float]:
    """Pull numeric fields from database rows for grounded reporting."""
    if not rows:
        return {}

    facts: dict[str, float] = {}
    if len(rows) == 1:
        for key, raw in rows[0].items():
            key_l = str(key).lower()
            if key_l in {"match_score", "similarity_score"} or key_l.endswith("_match_score"):
                continue
            parsed = _to_float(raw)
            if parsed is not None:
                facts[str(key)] = parsed
        return facts

    return {"_row_count": float(len(rows))}


def _is_whole_number(value: float) -> bool:
    return abs(value - round(value)) < 1e-9


def _format_scalar_value(value: float, *, prefer_integer: bool = False) -> str:
    if prefer_integer or _is_whole_number(value):
        return str(int(round(value)))
    return f"{value:.2f}"


def _is_count_query(user_query: str, column_key: str) -> bool:
    q = user_query.lower()
    key = column_key.lower()
    if any(
        phrase in q
        for phrase in (
            "how many",
            "number of",
            "count of",
            "total number",
            "how much many",
        )
    ):
        return True
    if key.startswith("count") or key in ("count", "cnt", "total_count"):
        return True
    return "count" in key or key.endswith("_count")


_ENTITY_PATTERNS: list[tuple[str, str, str]] = [
    (r"\bwarehouses?\b", "warehouse", "warehouses"),
    (r"\bcustomers?\b", "customer", "customers"),
    (r"\bproducts?\b", "product", "products"),
    (r"\borders?\b", "order", "orders"),
    (r"\bpart(?:y|ies)\b", "party", "parties"),
    (r"\bcategories?\b", "category", "categories"),
    (r"\bemployees?\b", "employee", "employees"),
    (r"\bskus?\b", "SKU", "SKUs"),
]


def _infer_count_entity(user_query: str, column_key: str) -> tuple[str, str] | None:
    """Return (singular, plural) entity names for a count-style answer."""
    q = user_query.lower()
    key = column_key.lower()

    for pattern, singular, plural in _ENTITY_PATTERNS:
        if re.search(pattern, q, re.IGNORECASE):
            return singular, plural

    for pattern, singular, plural in _ENTITY_PATTERNS:
        if re.search(pattern.replace(r"\b", ""), key):
            return singular, plural

    if "warehouse" in key:
        return "warehouse", "warehouses"
    if "customer" in key:
        return "customer", "customers"
    if "product" in key:
        return "product", "products"
    if "order" in key:
        return "order", "orders"

    return None


def _build_count_insight(
    user_query: str, value: float, singular: str, plural: str
) -> str:
    count = int(round(value))
    year = _year_phrase(user_query)
    if count == 1:
        return f"There is 1 {singular}{year}."
    return f"There are {count} {plural}{year}."


def _metric_label(column_key: str, user_query: str) -> str:
    q = user_query.lower()
    key = column_key.lower()

    if "revenue" in q or key in ("sum", "total_revenue", "revenue"):
        return "Total revenue"
    if "profit" in q:
        return "Total profit"
    if "order" in q and ("count" in q or "number" in q):
        return "Order count"
    if key.startswith("sum"):
        return "Total"
    if key.startswith("avg") or key.startswith("average"):
        return "Average"
    if key.startswith("count"):
        return "Count"

    return column_key.replace("_", " ").strip()


def _year_phrase(user_query: str) -> str:
    match = re.search(r"\b(20\d{2})\b", user_query)
    if match:
        return f" in {match.group(1)}"
    return ""


def build_grounded_insight(user_query: str, facts: dict[str, float]) -> str:
    """Format a short insight using exact database numbers (no LLM)."""
    year = _year_phrase(user_query)
    metric_facts = {k: v for k, v in facts.items() if not k.startswith("_")}

    if not metric_facts:
        return "No numeric results were returned from the database query."

    if len(metric_facts) == 1:
        key, value = next(iter(metric_facts.items()))
        if _is_count_query(user_query, key):
            entity = _infer_count_entity(user_query, key)
            if entity:
                singular, plural = entity
                return _build_count_insight(user_query, value, singular, plural)

        label = _metric_label(key, user_query)
        prefer_int = _is_count_query(user_query, key) or _is_whole_number(value)
        formatted = _format_scalar_value(value, prefer_integer=prefer_int)
        return f"{label}{year} is {formatted}."

    parts = []
    for k, v in metric_facts.items():
        prefer_int = _is_count_query(user_query, k) or _is_whole_number(v)
        parts.append(
            f"{_metric_label(k, user_query)} is "
            f"{_format_scalar_value(v, prefer_integer=prefer_int)}"
        )
    return f"Results{year}: " + ", ".join(parts) + "."


def try_grounded_insight(
    user_query: str,
    rows: list[dict[str, Any]],
    python_output: dict[str, Any] | None = None,
) -> str | None:
    """
    Return a deterministic insight when we have a single-row numeric aggregate.
    Returns None when the LLM path should be used (multi-row listings, etc.).
    """
    if len(rows) != 1:
        return None

    facts = (python_output or {}).get("verified_facts")
    if not isinstance(facts, dict) or not facts:
        facts = extract_verified_facts(rows)

    metric_facts = {k: v for k, v in facts.items() if not k.startswith("_")}
    if not metric_facts:
        return None

    return build_grounded_insight(user_query, metric_facts)


def try_empty_rows_insight(
    user_query: str,
    rows: list[dict[str, Any]],
) -> str | None:
    """Return a deterministic no-data message; never invent figures for zero rows."""
    if rows:
        return None
    year = ""
    m = re.search(r"\b(20\d{2})\b", user_query)
    if m:
        year = f" in {m.group(1)}"
    return (
        f"No records matched your question{year}. "
        "Nothing in the database currently matches the requested filters."
    )


_RANKING_QUERY_RE = re.compile(
    r"\b(top|bottom|highest|lowest|best|worst|leading|least)\b",
    re.IGNORECASE,
)

# Cap ranked insights when the query omits a number (e.g. "top products by revenue").
_DEFAULT_RANK_DISPLAY_LIMIT = 10


def _rows_for_ranked_insight(
    user_query: str, rows: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], int | None]:
    """Limit displayed rows to the N requested in the question."""
    requested = parse_rank_limit(user_query)
    if requested is not None and requested > 0:
        return rows[:requested], requested
    if _is_ranking_query(user_query):
        return rows[:_DEFAULT_RANK_DISPLAY_LIMIT], None
    return rows, None


def _is_ranking_query(user_query: str) -> bool:
    q = user_query.lower()
    return bool(_RANKING_QUERY_RE.search(q)) or bool(
        re.search(r"\btop\s+\d+\b", q)
    )


def _row_value_ci(row: dict[str, Any], *names: str) -> Any:
    """Get row value by column name (case-insensitive)."""
    lower_map = {str(k).lower(): v for k, v in row.items()}
    for name in names:
        val = lower_map.get(name.lower())
        if val is not None and str(val).strip():
            return val
    return None


def _query_implies_units_sold(user_query: str) -> bool:
    q = user_query.lower()
    if "revenue" in q:
        return False
    return any(
        phrase in q
        for phrase in (
            "selling",
            "seller",
            "sold",
            "best seller",
            "best-selling",
            "fast-moving",
            "fast moving",
            "fast mover",
            "units sold",
        )
    )


def _entity_label(row: dict[str, Any]) -> str:
    for key in (
        "product_name",
        "company_name",
        "name",
        "sku",
        "category",
        "contact_name",
    ):
        val = _row_value_ci(row, key)
        if val is not None:
            return str(val).strip()

    for row_key, val in row.items():
        if row_key.lower().endswith("_name") and val is not None and str(val).strip():
            return str(val).strip()

    sku = _row_value_ci(row, "sku")
    if sku is not None:
        return str(sku).strip()

    product_id = _row_value_ci(row, "product_id")
    if product_id is not None:
        return f"Product ID {product_id}"

    return "Unknown"


def _primary_metric(row: dict[str, Any], user_query: str) -> tuple[str, float] | None:
    """Pick the main numeric measure for ranked rows."""
    q = user_query.lower()
    preferred: list[str] = []
    if _query_implies_units_sold(user_query):
        preferred.extend(
            ["units_sold", "total_quantity", "quantity", "units", "total_units"]
        )
    if "revenue" in q:
        preferred.extend(
            ["revenue", "total_revenue", "product_revenue", "sum_revenue", "sum"]
        )
    if "profit" in q:
        preferred.extend(["profit", "total_profit", "margin"])
    if "quantity" in q or "units" in q:
        preferred.extend(["units_sold", "quantity", "total_quantity"])
    preferred.extend(
        [
            "revenue",
            "total_revenue",
            "sum",
            "total",
            "amount",
            "line_total",
            "outstanding_balance",
            "credit_limit",
        ]
    )

    seen: set[str] = set()
    for key in preferred:
        kl = key.lower()
        if kl in seen:
            continue
        seen.add(kl)
        for row_key, raw in row.items():
            if row_key.lower() == kl:
                parsed = _to_float(raw)
                if parsed is not None:
                    return row_key, parsed

    skip_suffixes = ("_id",)
    skip_keys = {"product_id", "customer_id", "order_id", "item_id", "inventory_id"}
    for key, raw in row.items():
        kl = key.lower()
        if kl in skip_keys or kl.endswith(skip_suffixes):
            continue
        parsed = _to_float(raw)
        if parsed is not None:
            return key, parsed
    return None


def _metric_phrase(user_query: str, metric_key: str) -> str:
    q = user_query.lower()
    mk = metric_key.lower()
    if _query_implies_units_sold(user_query) or mk in (
        "units_sold",
        "total_quantity",
        "quantity",
        "total_units",
        "units",
    ):
        return "units sold"
    if "revenue" in q or "revenue" in mk or mk == "total_revenue":
        return "revenue"
    if "profit" in q or "profit" in mk:
        return "profit"
    if "quantity" in q or "units" in mk:
        return "units sold"
    return metric_key.replace("_", " ")


def build_ranked_list_insight(user_query: str, rows: list[dict[str, Any]]) -> str:
    """Deterministic top-N style report from SQL rows (no LLM meta-language)."""
    display_rows, requested_n = _rows_for_ranked_insight(user_query, rows)
    if not display_rows:
        return "No results were returned for this ranking query."

    year = _year_phrase(user_query)
    title = user_query.strip().rstrip("?.")
    if title:
        title = title[0].upper() + title[1:]
    else:
        n = requested_n or len(display_rows)
        title = f"Top {n} results"

    lines = [f"{title}{year}:"]
    for rank, row in enumerate(display_rows, start=1):
        entity = _entity_label(row)
        metric = _primary_metric(row, user_query)
        if metric:
            _, value = metric
            phrase = _metric_phrase(user_query, metric[0])
            lines.append(f"{rank}. {entity} — {phrase} {value:.2f}")
        else:
            lines.append(f"{rank}. {_format_row_brief(row)}")
    return "\n".join(lines)


def try_ranked_list_insight(
    user_query: str,
    rows: list[dict[str, Any]],
) -> str | None:
    """Grounded insight for top/bottom-N listings (2+ rows, or top-1 with explicit N)."""
    if not rows:
        return None
    if parse_rank_limit(user_query) == 1 and len(rows) >= 1:
        pass
    elif len(rows) < 2:
        return None
    if not _is_ranking_query(user_query):
        return None
    if _primary_metric(rows[0], user_query) is None:
        return None
    return build_ranked_list_insight(user_query, rows)


_META_PREFIXES = (
    r"^Based on the provided (?:database )?sample rows,?\s*",
    r"^Based on the (?:provided )?data(?: sample)?,?\s*",
    r"^According to the (?:provided )?(?:database )?(?:sample )?rows?,?\s*",
    r"^From the (?:provided )?(?:database )?sample rows?,?\s*",
    r"^According to the database sample,?\s*",
    r"^From the sample data,?\s*",
)


def sanitize_insight_text(text: str) -> str:
    """Strip LLM meta-phrases; normalize escaped newlines."""
    cleaned = text.strip().replace("\\n", "\n")
    for pattern in _META_PREFIXES:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE).strip()
    cleaned = re.sub(
        r"\bmatch[_\s]?scores?\b[^.\n]*\.?",
        "",
        cleaned,
        flags=re.IGNORECASE,
    ).strip()
    return cleaned


def _coerce_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if value in (True, "true", "t", 1, "1", "yes"):
        return True
    if value in (False, "false", "f", 0, "0", "no"):
        return False
    return None


def try_boolean_attribute_insight(
    user_query: str,
    rows: list[dict[str, Any]],
) -> str | None:
    """Deterministic yes/no answer for boolean attribute lookups."""
    from app.planning.attribute_lookup import (
        extract_entity_phrase,
        resolve_boolean_attribute,
    )

    resolved = resolve_boolean_attribute(user_query)
    if not resolved or len(rows) != 1:
        return None

    _table, col = resolved
    val = _coerce_bool(_row_value_ci(rows[0], col))
    if val is None:
        return None

    entity_name = (
        _row_value_ci(rows[0], "product_name")
        or _row_value_ci(rows[0], "company_name")
        or extract_entity_phrase(user_query)
    )

    if col == "is_discontinued":
        return (
            f"{entity_name} is discontinued."
            if val
            else f"{entity_name} is not discontinued."
        )
    if col == "is_active":
        return (
            f"{entity_name} is active."
            if val
            else f"{entity_name} is not active."
        )

    label = col.replace("_", " ")
    return f"{entity_name} {label} is {'yes' if val else 'no'}."


def try_blocked_ambiguous_entity_insight(
    user_query: str,
    rows: list[dict[str, Any]],
) -> str | None:
    """Fallback when multiple entity matches should have triggered clarification."""
    from app.planning.attribute_lookup import expects_single_entity_answer

    if not expects_single_entity_answer(user_query) or len(rows) <= 1:
        return None
    return (
        "Several records match your question. "
        "Please specify which one you mean."
    )


def try_text_attribute_insight(
    user_query: str,
    rows: list[dict[str, Any]],
) -> str | None:
    """Deterministic insight for a single text attribute column (category, name, etc.)."""
    from app.planning.attribute_lookup import (
        extract_entity_phrase,
        extract_sku_code,
        requested_attribute_column,
    )

    attr_col = requested_attribute_column(user_query)
    if not attr_col or not rows:
        return None

    values: list[Any] = []
    for row in rows:
        val = _row_value_ci(row, attr_col)
        if val is not None and str(val).strip() != "":
            values.append(val)

    if not values:
        return None

    unique = {str(v).strip() for v in values}
    if len(unique) != 1:
        return None

    display_value = next(iter(unique))
    attr_label = attr_col.replace("_", " ")
    ref = extract_sku_code(user_query) or extract_entity_phrase(user_query)
    return f"The {attr_label} for {ref} is {display_value}."


def _measure_phrase_from_query(user_query: str) -> str:
    patterns = (
        r"\bhas\s+(?:the\s+)?(?:highest|lowest|maximum|minimum|max|min|most|least)\s+"
        r"(\w+(?:\s+\w+)?)",
        r"\b(?:highest|lowest|maximum|minimum|max|min|most|least)\s+(\w+(?:\s+\w+)?)",
    )
    for pattern in patterns:
        match = re.search(pattern, user_query, re.IGNORECASE)
        if match:
            return match.group(1).lower().strip()
    return "value"


def _extremum_direction(user_query: str) -> str:
    q = user_query.lower()
    if re.search(r"\b(highest|maximum|max|most|top)\b", q):
        return "highest"
    if re.search(r"\b(lowest|minimum|min|least|bottom)\b", q):
        return "lowest"
    return "highest"


def _record_label_for_query(row: dict[str, Any], user_query: str) -> str:
    q = user_query.lower()
    noun_specs = (
        (r"\border", "order_id", "Order"),
        (r"\bcustomer", "customer_id", "Customer"),
        (r"\bemployee", "employee_id", "Employee"),
        (r"\bproduct", "product_id", "Product"),
        (r"\bpayslip", "payslip_id", "Payslip"),
    )
    for pattern, col, prefix in noun_specs:
        if re.search(pattern, q):
            val = _row_value_ci(row, col)
            if val is not None:
                return f"{prefix} {val}"
    label = _entity_label(row)
    if label != "Unknown":
        return label
    for col in ("order_id", "customer_id", "employee_id", "product_id"):
        val = _row_value_ci(row, col)
        if val is not None:
            return f"{col.replace('_', ' ').title()} {val}"
    return "The matching record"


def try_extremum_insight(
    user_query: str,
    rows: list[dict[str, Any]],
) -> str | None:
    """Deterministic insight for which/what … highest/lowest … single-row SQL answers."""
    if not rows or len(rows) > 5:
        return None
    q = user_query.lower()
    if not _RANKING_QUERY_RE.search(q) and not re.search(
        r"\b(which|what)\b.*\b(highest|lowest|maximum|minimum|max|min|most|least)\b",
        q,
    ):
        return None
    if len(rows) >= 2 and parse_rank_limit(user_query):
        return None

    direction = _extremum_direction(user_query)
    measure = _measure_phrase_from_query(user_query)
    row = rows[0]
    label = _record_label_for_query(row, user_query)
    metric = _primary_metric(row, user_query)

    if metric:
        _, value = metric
        return f"{label} has the {direction} {measure} at {_format_number(value)}."

    return f"{label} has the {direction} {measure}."


def try_deterministic_insight(
    user_query: str,
    rows: list[dict[str, Any]],
    python_output: dict[str, Any] | None = None,
) -> str | None:
    """Prefer grounded scalar, boolean/text attribute, then ranked lists; None → LLM synthesizer."""
    boolean = try_boolean_attribute_insight(user_query, rows)
    if boolean:
        return boolean
    extremum = try_extremum_insight(user_query, rows)
    if extremum:
        return extremum
    text_attr = try_text_attribute_insight(user_query, rows)
    if text_attr:
        return text_attr
    scalar = try_grounded_insight(user_query, rows, python_output)
    if scalar:
        return scalar
    ranked = try_ranked_list_insight(user_query, rows)
    if ranked:
        return ranked
    blocked = try_blocked_ambiguous_entity_insight(user_query, rows)
    if blocked:
        return blocked
    return None


def _is_fast_mover_low_stock_target(target_id: str, label: str, user_query: str) -> bool:
    """Identify fast-mover stock target from id/label first (not the full user question)."""
    tid = target_id.lower()
    label_l = label.lower()
    if (
        ("fast" in tid and ("stock" in tid or "mov" in tid))
        or ("low" in tid and "stock" in tid)
        or ("inventory" in tid and "stock" in tid)
        or ("fast" in label_l and ("stock" in label_l or "mov" in label_l))
        or ("low" in label_l and "stock" in label_l)
    ):
        return True
    if "credit" in tid or "customer" in tid:
        return False
    q = user_query.lower()
    return (
        ("fast" in q and "moving" in q and "stock" in q)
        or ("fast" in q and "low" in q and "stock" in q)
    )


def _classify_target(target_id: str, label: str) -> str:
    """
    Classify a multi-step target from id/label only (never the full user question).
    Avoids mis-labeling SKU sections when the combined query also mentions credit.
    """
    tid = target_id.lower()
    label_l = label.lower()

    if _is_fast_mover_low_stock_target(target_id, label, ""):
        return "fast_mover"
    if tid in ("sku_stock_by_warehouse", "sku_stock", "sku_inventory") or (
        "sku" in tid and ("stock" in tid or "invent" in tid)
    ):
        return "sku_stock"
    if "sku" in label_l and ("stock" in label_l or "inventory" in label_l):
        return "sku_stock"
    if tid in (
        "high_credit_outstanding",
        "credit_parties",
        "high_credit_parties",
    ) or (
        "outstanding" in tid
        or ("outstanding" in label_l and "credit" in label_l)
    ):
        return "credit_outstanding"
    if _is_credit_limit_only_target(target_id, label):
        return "credit_limit"
    if "credit" in tid or "customer" in tid or "party" in tid:
        return "credit"
    return "generic"


def _is_credit_limit_only_target(target_id: str, label: str) -> bool:
    tid = target_id.lower()
    label_l = label.lower()
    return tid in ("high_credit_customers", "high_credit_limit", "credit_limit_customers") or (
        "credit" in tid
        and ("customer" in tid or "credit" in label_l)
        and "outstanding" not in tid
        and "outstanding" not in label_l
    )


def _is_sku_stock_target(target_id: str, label: str, user_query: str) -> bool:
    if _is_fast_mover_low_stock_target(target_id, label, user_query):
        return False
    tid = target_id.lower()
    label_l = label.lower()
    if tid in ("sku_stock_by_warehouse", "sku_stock", "sku_inventory"):
        return True
    return ("sku" in tid and ("stock" in tid or "invent" in tid)) or (
        "sku" in label_l and ("stock" in label_l or "inventory" in label_l)
    )


def _sku_display_name(label: str, user_query: str) -> str:
    return parse_sku(label) or parse_sku(user_query) or "the requested SKU"


def _build_sku_stock_section(
    rows: list[dict[str, Any]], user_query: str, label: str = ""
) -> str:
    sku_name = _sku_display_name(label, user_query)
    if not rows:
        return (
            f"No inventory rows were found for {sku_name}. "
            "Verify the SKU exists in products and has warehouse stock."
        )

    first = rows[0]
    name = first.get("product_name") or first.get("sku") or "Unknown product"
    sku = first.get("sku") or ""
    lines = [f"Stock for {name}" + (f" (SKU {sku})" if sku else "") + " by warehouse:"]
    for row in rows:
        warehouse = row.get("warehouse_name") or "Unknown warehouse"
        on_hand = _format_number(row.get("stock_on_hand"))
        available = row.get("available_stock")
        if available is None:
            soh = _to_float(row.get("stock_on_hand"))
            alloc = _to_float(row.get("allocated_stock"))
            if soh is not None and alloc is not None:
                available = soh - alloc
        lines.append(
            f"   - {warehouse}: on hand {on_hand}, "
            f"available {_format_number(available)}, "
            f"reorder level {_format_number(row.get('reorder_level'))}"
        )
    return "\n".join(lines)


def _is_credit_target(target_id: str, label: str, user_query: str) -> bool:
    kind = _classify_target(target_id, label)
    if kind in ("fast_mover", "sku_stock", "generic"):
        if kind != "generic":
            return False
        q = user_query.lower()
        return "credit" in q and "limit" in q
    return kind in ("credit", "credit_limit", "credit_outstanding")


def _row_is_low_stock(row: dict[str, Any]) -> bool:
    val = row.get("is_low_stock")
    if isinstance(val, bool):
        return val
    if val in (True, "true", "t", 1, "1"):
        return True
    avail = _to_float(row.get("available_stock"))
    reorder = _to_float(row.get("reorder_level"))
    if avail is not None and reorder is not None:
        return avail <= reorder
    return False


def _group_fast_mover_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Aggregate warehouse rows into top products sorted by units_sold."""
    by_product: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = str(row.get("product_id") or row.get("sku") or "unknown")
        if key not in by_product:
            by_product[key] = {
                "product_id": row.get("product_id"),
                "sku": row.get("sku"),
                "product_name": row.get("product_name"),
                "units_sold": _to_float(row.get("units_sold")) or 0.0,
                "warehouse_rows": [],
            }
        units = _to_float(row.get("units_sold"))
        if units is not None and units > by_product[key]["units_sold"]:
            by_product[key]["units_sold"] = units
        by_product[key]["warehouse_rows"].append(row)

    return sorted(
        by_product.values(),
        key=lambda p: p["units_sold"],
        reverse=True,
    )[:3]


def _fast_movers_summary_from_rows(rows: list[dict[str, Any]]) -> str:
    products = _group_fast_mover_rows(rows)
    if not products:
        return "Top 3 fast-moving products could not be determined (no inventory rows)."

    any_low = any(
        _row_is_low_stock(wh) for p in products for wh in p["warehouse_rows"]
    )
    if any_low:
        return (
            "Top 3 fast-moving products are listed below; at least one is low on stock "
            "in a warehouse."
        )
    return (
        "Top 3 fast-moving products are listed below; none are low on stock in any warehouse."
    )


def _build_fast_movers_section(rows: list[dict[str, Any]], user_query: str) -> str:
    """List top 3 fast movers with per-warehouse stock and low-stock verdict."""
    year = _year_phrase(user_query)
    products = _group_fast_mover_rows(rows)

    if not products:
        return (
            f"No inventory data was found for the top fast-moving products{year}. "
            "Sales ranking could not be joined to warehouse stock."
        )

    lines = [
        f"Top 3 fast-moving products{year} (by units sold) and stock across warehouses:"
    ]
    any_low = False

    for rank, product in enumerate(products, start=1):
        name = product.get("product_name") or product.get("sku") or "Unknown product"
        sku = product.get("sku")
        units = product["units_sold"]
        title = f"   {rank}. {name}"
        if sku:
            title += f" (SKU {sku})"
        title += f", units sold {units:.2f}"
        lines.append(title)

        if not product["warehouse_rows"]:
            lines.append("      - No warehouse inventory rows found for this product.")
            continue

        for wh_row in product["warehouse_rows"]:
            warehouse = wh_row.get("warehouse_name") or "Unknown warehouse"
            available = _format_number(wh_row.get("available_stock"))
            reorder = _format_number(wh_row.get("reorder_level"))
            is_low = _row_is_low_stock(wh_row)
            if is_low:
                any_low = True
            status = "LOW STOCK" if is_low else "OK"
            lines.append(
                f"      - {warehouse}: available {available}, "
                f"reorder level {reorder} [{status}]"
            )

    if any_low:
        lines.append(
            "Conclusion: At least one of these top 3 fast-moving products is running "
            "low on stock in at least one warehouse."
        )
    else:
        lines.append(
            "Conclusion: None of the top 3 fast-moving products are running low on "
            "stock in any warehouse."
        )

    return "\n".join(lines)


def _zero_row_message(target_id: str, label: str, user_query: str) -> str:
    """Business-friendly text when a successful query returns no rows."""
    year = _year_phrase(user_query)
    kind = _classify_target(target_id, label)

    if kind == "fast_mover":
        return (
            f"Top 3 fast-moving products{year} could not be listed: the query returned "
            "no inventory rows (check that sales and inventory data exist for the period)."
        )

    if kind == "sku_stock":
        return _build_sku_stock_section([], user_query, label)

    if kind == "credit_limit":
        threshold = parse_credit_threshold(f"{label} {user_query}")
        return (
            f"No customers{year} have a credit limit of {threshold:.0f} or above."
        )

    if kind == "credit_outstanding":
        return (
            f"No customers{year} have a credit limit above 5 Lakhs while also carrying "
            "an outstanding balance."
        )

    return (
        f"The query for this part completed successfully but returned no rows{year}. "
        "Nothing in the database currently matches the requested filters."
    )


def _success_headline(
    target_id: str, label: str, user_query: str, row_count: int
) -> str:
    """Opening sentence for a section with data."""
    year = _year_phrase(user_query)

    if _is_credit_limit_only_target(target_id, label):
        threshold = parse_credit_threshold(user_query)
        word = "customer" if row_count == 1 else "customers"
        return (
            f"{row_count} {word}{year} have a credit limit of {threshold:.0f} or above."
        )

    if _is_credit_target(target_id, label, user_query):
        party_word = "party" if row_count == 1 else "parties"
        return (
            f"{row_count} {party_word}{year} have a credit limit above 5 Lakhs "
            f"and still have an outstanding balance."
        )

    if _is_sku_stock_target(target_id, label, user_query):
        wh_word = "warehouse" if row_count == 1 else "warehouses"
        return f"Stock is reported across {row_count} {wh_word} for the requested SKU."

    if _is_fast_mover_low_stock_target(target_id, label, user_query):
        if row_count == 1:
            return (
                f"1 fast-moving product{year} is running low on stock in at least "
                "one warehouse."
            )
        return (
            f"{row_count} warehouse line(s){year} show low stock for top fast-moving "
            "products (available stock at or below reorder level)."
        )

    record_word = "record" if row_count == 1 else "records"
    return f"{row_count} {record_word}{year} match the criteria for: {label}."


def _format_row_for_target(target_id: str, label: str, row: dict[str, Any]) -> str:
    kind = _classify_target(target_id, label)
    if kind in ("credit", "credit_limit", "credit_outstanding"):
        company = row.get("company_name") or "Unknown company"
        contact = row.get("contact_name")
        credit = _format_number(row.get("credit_limit"))
        outstanding = _format_number(row.get("outstanding_balance"))
        line = f"{company} (credit limit {credit}, outstanding {outstanding}"
        if contact:
            line += f", contact {contact}"
        return line + ")"

    if _is_sku_stock_target(target_id, label, ""):
        warehouse = row.get("warehouse_name") or "Unknown warehouse"
        return (
            f"{row.get('sku') or 'SKU'} at {warehouse}: on hand "
            f"{_format_number(row.get('stock_on_hand'))}, available "
            f"{_format_number(row.get('available_stock'))}"
        )

    if _is_fast_mover_low_stock_target(target_id, label, ""):
        sku = row.get("sku") or row.get("product_name") or "Unknown SKU"
        warehouse = row.get("warehouse_name") or "Unknown warehouse"
        available = row.get("available_stock")
        if available is None:
            soh = _to_float(row.get("stock_on_hand"))
            alloc = _to_float(row.get("allocated_stock"))
            if soh is not None and alloc is not None:
                available = soh - alloc
        reorder = row.get("reorder_level")
        units = row.get("units_sold")
        parts = [f"{sku} at {warehouse}", f"available {_format_number(available)}"]
        if reorder is not None:
            parts.append(f"reorder level {_format_number(reorder)}")
        if units is not None:
            parts.append(f"units sold {_format_number(units)}")
        return ", ".join(parts)

    return _format_row_brief(row)


def _format_row_brief(row: dict[str, Any], max_fields: int = 6) -> str:
    parts = []
    for idx, (key, val) in enumerate(row.items()):
        if idx >= max_fields:
            break
        if val is None:
            continue
        parts.append(f"{key}={_format_number(val)}")
    return ", ".join(parts)


def _section_summary_line(
    target_id: str,
    label: str,
    user_query: str,
    row_count: int,
    rows: list[dict[str, Any]] | None = None,
) -> str:
    """One-line outcome for executive summary (per target, id/label only)."""
    kind = _classify_target(target_id, label)

    if row_count == 0:
        if kind == "fast_mover":
            return (
                "Top 3 fast-moving products could not be listed (no inventory rows returned)."
            )
        if kind == "sku_stock":
            sku = _sku_display_name(label, user_query)
            return f"No warehouse stock found for {sku}."
        if kind == "credit_limit":
            return "No customers meet the requested credit limit threshold."
        if kind == "credit_outstanding":
            return "No parties meet the high-credit with outstanding-balance criteria."
        return f"{label}: no matching data."

    if kind == "credit_limit":
        threshold = parse_credit_threshold(f"{label} {user_query}")
        word = "customer" if row_count == 1 else "customers"
        return f"{row_count} {word} have credit limit >= {threshold:.0f}."

    if kind == "credit_outstanding":
        party_word = "party" if row_count == 1 else "parties"
        return (
            f"{row_count} {party_word} have credit above 5 Lakhs with outstanding balance."
        )

    if kind == "sku_stock":
        sku = _sku_display_name(label, user_query)
        wh_word = "warehouse" if row_count == 1 else "warehouses"
        return f"{sku} has stock data across {row_count} {wh_word}."

    if kind == "fast_mover":
        return _fast_movers_summary_from_rows(rows or [])

    return f"{label}: {row_count} matching record(s)."


def _build_executive_summary(
    user_query: str,
    target_results: dict[str, dict[str, Any]],
    ordered_ids: list[str],
    labels: dict[str, str],
) -> str:
    lines: list[str] = []
    for tid in ordered_ids:
        bundle = target_results.get(tid)
        label = labels.get(tid, tid)
        if bundle is None:
            lines.append(f"{label} could not be completed.")
            continue
        if bundle.get("status") != "success":
            lines.append(f"{label} failed.")
            continue
        rows = bundle.get("rows") or []
        row_count = int(bundle.get("row_count", len(rows)))
        lines.append(_section_summary_line(tid, label, user_query, row_count, rows))

    if not lines:
        return ""

    if len(lines) == 1:
        return f"Summary: {lines[0]}"

    return "Summary: " + " ".join(f"({idx}) {line}" for idx, line in enumerate(lines, 1))


def build_multi_target_insight(
    user_query: str,
    target_results: dict[str, dict[str, Any]],
    planned_targets: list[dict[str, Any]] | None = None,
) -> str:
    """Deterministic sectioned report from per-target SQL results."""
    ordered_ids: list[str] = []
    labels: dict[str, str] = {}
    if planned_targets:
        for t in planned_targets:
            tid = t.get("id", "")
            if tid:
                ordered_ids.append(tid)
                labels[tid] = t.get("label", tid)
    if not ordered_ids:
        ordered_ids = list(target_results.keys())

    if not ordered_ids and not target_results:
        return "No results were returned for any part of the query."

    summary = _build_executive_summary(
        user_query, target_results, ordered_ids, labels
    )

    sections: list[str] = []
    for idx, tid in enumerate(ordered_ids, start=1):
        bundle = target_results.get(tid)
        if bundle is None:
            label = labels.get(tid, tid)
            sections.append(
                f"{idx}. {label}\n"
                "This part was not completed (SQL validation or execution stopped "
                "before this step)."
            )
            continue

        label = bundle.get("label", labels.get(tid, tid))
        rows = bundle.get("rows") or []
        row_count = int(bundle.get("row_count", len(rows)))
        status = bundle.get("status", "success")

        if status != "success":
            sections.append(
                f"{idx}. {label}\n"
                f"Query failed: {bundle.get('error', 'unknown error')}."
            )
            continue

        if row_count == 0:
            sections.append(f"{idx}. {label}\n{_zero_row_message(tid, label, user_query)}")
            continue

        if _is_fast_mover_low_stock_target(tid, label, user_query):
            sections.append(
                f"{idx}. {label}\n{_build_fast_movers_section(rows, user_query)}"
            )
            continue

        if _is_sku_stock_target(tid, label, user_query):
            sections.append(
                f"{idx}. {label}\n{_build_sku_stock_section(rows, user_query, label)}"
            )
            continue

        # Avoid repeating counts already stated in the executive summary.
        lines = [f"{idx}. {label}"]
        show = min(row_count, 10)
        for row_idx, row in enumerate(rows[:show], start=1):
            lines.append(f"   {row_idx}. {_format_row_for_target(tid, label, row)}")
        if row_count > show:
            lines.append(f"   ... and {row_count - show} more.")
        sections.append("\n".join(lines))

    body = "\n\n".join(sections)
    if summary:
        return f"{summary}\n\n{body}"
    return body


def try_multi_target_insight(
    query_mode: str,
    user_query: str,
    target_results: dict[str, dict[str, Any]] | None,
    planned_targets: list[dict[str, Any]] | None = None,
) -> str | None:
    if query_mode != "MULTI_STEP":
        return None
    if not target_results and not planned_targets:
        return None
    return build_multi_target_insight(
        user_query,
        target_results or {},
        planned_targets=planned_targets,
    )
