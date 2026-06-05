"""Pre-execution SQL guardrails: syntax, schema, policy, complexity."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import sqlglot
from sqlglot import exp

from app.config import SQL_COMPLEXITY_MAX_JOINS, SQL_ROW_LIMIT
from app.schema.column_filter import allows_fuzzy_match
from app.schema.loader import allowed_columns, allowed_tables

FORBIDDEN_PATTERNS = [
    (r"\b(DROP|DELETE|UPDATE|INSERT|ALTER|TRUNCATE|CREATE|GRANT|REVOKE)\b", "write operation"),
    (r";\s*\w", "multiple statements"),
    (r"--", "SQL comments"),
    (r"/\*", "block comments"),
]

READ_ONLY_REQUIRED = True

_FUZZY_SIMILARITY_RE = re.compile(
    r"strict_word_similarity\s*\(\s*[^,]+,\s*(?:[\w]+\.)?(\w+)\s*\)",
    re.IGNORECASE,
)


@dataclass
class ValidationResult:
    passed: bool
    syntax_ok: bool = True
    schema_ok: bool = True
    policy_ok: bool = True
    complexity_score: int = 0
    issues: list[str] = field(default_factory=list)
    error_code: str | None = None

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "syntax_ok": self.syntax_ok,
            "schema_ok": self.schema_ok,
            "policy_ok": self.policy_ok,
            "complexity_score": self.complexity_score,
            "issues": self.issues,
            "error_code": self.error_code,
        }


def _normalize_sql(sql: str) -> str:
    return sql.strip().rstrip(";")


def _is_select_wrapper(node: exp.Expression) -> bool:
    if isinstance(node, exp.Select):
        return True
    if isinstance(node, (exp.Subquery, exp.Union)):
        return True
    if isinstance(node, exp.With) and node.this:
        return _is_select_wrapper(node.this)
    return False


def _root_select(node: exp.Expression) -> exp.Select | None:
    """Return the outermost SELECT to attach LIMIT / emit SQL for RPC execution."""
    if isinstance(node, exp.Select):
        return node
    if isinstance(node, exp.With) and node.this:
        return _root_select(node.this)
    if isinstance(node, exp.Subquery) and node.this:
        return _root_select(node.this)
    if isinstance(node, exp.Union):
        return _root_select(node.this) if node.this else None
    return None


def _parse_postgres_tree(sql: str) -> exp.Expression:
    return sqlglot.parse_one(_normalize_sql(sql), dialect="postgres")


def normalize_sql_for_execution(
    sql: str,
    *,
    row_limit: int | None = None,
) -> str:
    """
    Parse and canonicalize SQL for Supabase execute_raw_sql RPC.
    Strips trailing semicolons and injects LIMIT when missing.
    """
    limit = row_limit if row_limit is not None else SQL_ROW_LIMIT
    tree = _parse_postgres_tree(sql)

    if not _is_select_wrapper(tree):
        raise ValueError("Only a single SELECT statement can be executed")

    root = _root_select(tree)
    if root is not None and not root.args.get("limit"):
        root.limit(limit, copy=False)

    executable = tree.sql(dialect="postgres").strip()
    return executable.rstrip(";")


def _extract_tables_aliases_and_columns(
    tree: exp.Expression,
) -> tuple[set[str], dict[str, str], set[tuple[str, str]]]:
    """Return real table names, alias->table map, and (table_or_alias, column) refs."""
    tables: set[str] = set()
    alias_to_table: dict[str, str] = {}

    for table in tree.find_all(exp.Table):
        name = (table.name or "").lower()
        alias = (table.alias_or_name or "").lower()
        if name:
            tables.add(name)
            if alias and alias != name:
                alias_to_table[alias] = name
            alias_to_table[name] = name

    columns: set[tuple[str, str]] = set()
    for col in tree.find_all(exp.Column):
        table_ref = (col.table or "").lower()
        col_name = (col.name or "").lower()
        if col_name:
            columns.add((table_ref, col_name))

    return tables, alias_to_table, columns


def _count_joins(tree: exp.Expression) -> int:
    return len(list(tree.find_all(exp.Join)))


def _extract_cte_aliases(tree: exp.Expression) -> set[str]:
    """CTE names declared in WITH clauses (not physical tables)."""
    names: set[str] = set()
    for with_node in tree.find_all(exp.With):
        for cte in with_node.expressions or []:
            if isinstance(cte, exp.CTE) and cte.alias:
                names.add(cte.alias.lower())
    return names


def _validate_fuzzy_similarity_columns(
    sql: str,
    issues: list[str],
) -> bool:
    """Reject strict_word_similarity on numeric/id/code columns."""
    ok = True
    for match in _FUZZY_SIMILARITY_RE.finditer(sql):
        col = match.group(1).lower()
        candidate_tables = [
            t for t in allowed_tables() if col in allowed_columns(t)
        ]
        if not candidate_tables:
            continue
        if all(not allows_fuzzy_match(table, col) for table in candidate_tables):
            issues.append(
                f"Policy violation: strict_word_similarity not allowed on "
                f"non-text column '{col}' (use exact = for ids/codes/numerics)"
            )
            ok = False
    return ok


def validate_sql(sql: str) -> ValidationResult:
    """Run Phase 1 pre-execution checks on generated SQL."""
    issues: list[str] = []
    result = ValidationResult(passed=True)

    if not sql or not sql.strip():
        return ValidationResult(
            passed=False,
            syntax_ok=False,
            issues=["SQL is empty"],
            error_code="SQL_VALIDATION",
        )

    normalized = _normalize_sql(sql)

    # Policy: forbidden patterns
    for pattern, label in FORBIDDEN_PATTERNS:
        if re.search(pattern, normalized, re.IGNORECASE):
            issues.append(f"Policy violation: {label} not allowed")
            result.policy_ok = False

    if "SELECT" not in normalized.upper():
        issues.append("Only SELECT queries are permitted")
        result.policy_ok = False

    if not _validate_fuzzy_similarity_columns(normalized, issues):
        result.policy_ok = False

    # Parse syntax via SQLGlot
    try:
        parsed = _parse_postgres_tree(sql)
    except Exception as exc:
        return ValidationResult(
            passed=False,
            syntax_ok=False,
            issues=[f"Syntax parse failed: {exc}"],
            error_code="SQL_VALIDATION",
        )

    if not isinstance(parsed, exp.Select) and not _is_select_wrapper(parsed):
        issues.append("Query must be a single SELECT statement")
        result.policy_ok = False

    # Schema: tables and columns (resolve aliases to real table names)
    tables, alias_map, columns = _extract_tables_aliases_and_columns(parsed)
    allowed_t = allowed_tables()
    cte_aliases = _extract_cte_aliases(parsed)

    unknown_tables = tables - allowed_t - cte_aliases
    if unknown_tables:
        allowed_list = ", ".join(sorted(allowed_t))
        issues.append(f"Unknown tables: {', '.join(sorted(unknown_tables))}")
        issues.append(
            f"Allowed physical tables only: {allowed_list}. "
            "CTE aliases (e.g. fast_movers) must be declared with WITH ... AS (...), "
            "never used as FROM/JOIN tables without a WITH clause."
        )
        result.schema_ok = False

    for table_ref, col in columns:
        if not table_ref:
            continue
        resolved = alias_map.get(table_ref, table_ref)
        if resolved in cte_aliases or table_ref in cte_aliases:
            continue
        if resolved not in allowed_t:
            issues.append(
                f"Unknown table reference: {table_ref}. "
                f"Use only: {', '.join(sorted(allowed_t))}."
            )
            result.schema_ok = False
            continue
        if col not in allowed_columns(resolved):
            issues.append(f"Unknown column {resolved}.{col}")
            result.schema_ok = False

    # Complexity
    join_count = _count_joins(parsed)
    result.complexity_score = join_count
    if join_count > SQL_COMPLEXITY_MAX_JOINS:
        issues.append(
            f"Query complexity too high: {join_count} joins (max {SQL_COMPLEXITY_MAX_JOINS})"
        )
        result.policy_ok = False

    root = _root_select(parsed)
    if root is not None and not root.args.get("limit"):
        issues.append(
            f"Advisory: LIMIT {SQL_ROW_LIMIT} will be applied automatically before execution"
        )

    result.issues = issues
    blocking_prefixes = (
        "Policy violation",
        "Only SELECT",
        "Unknown tables",
        "Unknown table reference",
        "Unknown column",
        "Query complexity",
    )
    result.passed = (
        result.syntax_ok
        and result.schema_ok
        and result.policy_ok
        and not any(i.startswith(blocking_prefixes) for i in issues)
    )

    if not result.passed:
        result.error_code = "SCHEMA_MISMATCH" if not result.schema_ok else "SQL_VALIDATION"

    return result
