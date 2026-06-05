"""Tests for entity disambiguation on ambiguous single-entity lookups."""

from unittest.mock import patch

from app.planning.disambiguation import (
    _build_natural_label,
    build_resolved_entity_sql,
    evaluate_disambiguation,
    is_intentional_multi_row_query,
    _fix_disambiguation_sql,
)
from app.planning.sql_shape import analyze_sql_shape, is_ambiguous_single_entity_lookup
from app.schema.entity_metadata import get_entity_metadata


def test_intentional_aggregate_skips_disambiguation():
    assert is_intentional_multi_row_query("What is the total salary by department?")


def test_fix_disambiguation_sql_rewrites_select():
    entity = get_entity_metadata("employees")
    assert entity is not None
    sql = (
        "SELECT salary FROM employees "
        "WHERE first_name = 'Diya' AND last_name = 'Sharma' LIMIT 10"
    )
    fixed = _fix_disambiguation_sql(sql, entity)
    assert fixed is not None
    assert "employee_id" in fixed
    assert "first_name" in fixed
    assert "WHERE first_name = 'Diya'" in fixed


def test_sql_shape_detects_scalar_employee_lookup():
    sql = (
        "SELECT salary FROM employees "
        "WHERE first_name = 'Diya' AND last_name = 'Sharma' LIMIT 10"
    )
    shape = analyze_sql_shape(sql)
    assert shape is not None
    assert shape.primary_table == "employees"
    assert "salary" in shape.select_columns
    entity = get_entity_metadata("employees")
    assert entity is not None
    assert is_ambiguous_single_entity_lookup(shape, entity, [{"salary": 1}, {"salary": 2}])


def test_evaluate_disambiguation_with_enriched_rows():
    sql = (
        "SELECT salary FROM employees "
        "WHERE first_name = 'Diya' AND last_name = 'Sharma' LIMIT 10"
    )
    scalar_rows = [{"salary": 100}, {"salary": 200}, {"salary": 300}]
    enriched = [
        {
            "employee_id": 1,
            "first_name": "Diya",
            "last_name": "Sharma",
            "job_title": "Analyst",
        },
        {
            "employee_id": 2,
            "first_name": "Diya",
            "last_name": "Sharma",
            "job_title": "Manager",
        },
    ]
    with patch(
        "app.planning.disambiguation.fetch_entity_rows_for_disambiguation",
        return_value=enriched,
    ):
        payload = evaluate_disambiguation(
            "What is the salary of Diya Sharma?",
            scalar_rows,
            sql,
            {},
        )
    assert payload is not None
    assert payload.parameter == "employee_id"
    assert payload.original_phrase == "Diya Sharma"
    assert len(payload.options) == 2
    assert payload.options[0].value == "1"
    assert payload.options[0].label == "Diya Sharma — Analyst"
    assert "employee_id" not in payload.options[0].label
    assert "resolved_filters" not in payload.message
    assert "Please select" in payload.message


def test_evaluate_disambiguation_skips_aggregate_query():
    sql = (
        "SELECT dept_id, SUM(salary) AS total FROM employees "
        "GROUP BY dept_id LIMIT 10"
    )
    rows = [{"dept_id": 1, "total": 100}, {"dept_id": 2, "total": 200}]
    payload = evaluate_disambiguation(
        "What is the total salary by department?",
        rows,
        sql,
        {},
    )
    assert payload is None


def test_resolved_filter_skips_disambiguation():
    sql = "SELECT salary FROM employees WHERE employee_id = '1' LIMIT 10"
    rows = [{"salary": 100}]
    payload = evaluate_disambiguation(
        "What is the salary of Diya Sharma?",
        rows,
        sql,
        {"employee_id": "1"},
    )
    assert payload is None


def test_natural_employee_label_omits_schema_fields():
    entity = get_entity_metadata("employees")
    assert entity is not None
    label = _build_natural_label(
        entity,
        {
            "employee_id": 3,
            "first_name": "Diya",
            "last_name": "Sharma",
            "job_title": "Business Analyst",
            "dept_id": 4,
            "email": "emp.3@example.com",
        },
    )
    assert label == "Diya Sharma — Business Analyst"
    assert "employee_id" not in label
    assert "dept_id" not in label
    assert "email" not in label


def test_build_resolved_employee_salary_sql_preserves_projection():
    original = (
        "SELECT salary FROM employees "
        "WHERE first_name = 'Diya' AND last_name = 'Sharma' LIMIT 10"
    )
    sql = build_resolved_entity_sql(
        "What is the salary of Diya Sharma?",
        {"employee_id": "42"},
        original,
    )
    assert sql is not None
    assert "employee_id = '42'" in sql
    assert "SELECT salary" in sql


def test_build_resolved_customer_sql():
    entity = get_entity_metadata("customers")
    assert entity is not None
    sql = build_resolved_entity_sql(
        "What is the credit limit for Acme?",
        {"customer_id": "7"},
        "SELECT credit_limit FROM customers WHERE company_name = 'Acme' LIMIT 10",
    )
    assert sql is not None
    assert "customer_id = '7'" in sql
    assert "credit_limit" in sql
