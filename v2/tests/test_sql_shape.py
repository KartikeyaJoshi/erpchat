"""Tests for structural SQL shape analysis."""

from app.planning.sql_shape import analyze_sql_shape, is_ambiguous_single_entity_lookup
from app.schema.entity_metadata import get_entity_metadata


def test_analyze_simple_select():
    sql = "SELECT salary FROM public.employees WHERE first_name = 'A' LIMIT 10"
    shape = analyze_sql_shape(sql)
    assert shape is not None
    assert shape.primary_table == "employees"
    assert shape.select_columns == ("salary",)
    assert "first_name" in shape.where_columns
    assert not shape.has_group_by
    assert not shape.has_aggregates


def test_analyze_group_by_not_ambiguous():
    sql = "SELECT dept_id, SUM(salary) AS total FROM employees GROUP BY dept_id"
    shape = analyze_sql_shape(sql)
    entity = get_entity_metadata("employees")
    assert shape is not None
    assert entity is not None
    assert shape.has_group_by
    assert not is_ambiguous_single_entity_lookup(
        shape, entity, [{"total": 1}, {"total": 2}]
    )
