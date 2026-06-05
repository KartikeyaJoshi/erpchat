from app.sql.entity_match_sql import EntityFilterSpec, build_entity_match_sql


def test_build_entity_match_sql_uses_strict_similarity():
    spec = EntityFilterSpec(
        query_kind="warehouse_stock",
        parameter="warehouse_name",
        table="inventory",
        column="warehouse_name",
        phrase="Mumbai Warehouse",
    )
    sql = build_entity_match_sql(spec)
    assert "strict_word_similarity" in sql
    assert "Mumbai Warehouse" in sql
    assert "match_score" in sql


def test_build_entity_match_sql_uses_exact_when_resolved():
    spec = EntityFilterSpec(
        query_kind="warehouse_stock",
        parameter="warehouse_name",
        table="inventory",
        column="warehouse_name",
        phrase="Mumbai Warehouse",
    )
    sql = build_entity_match_sql(
        spec,
        resolved_filters={"warehouse_name": "MUMBAI-WH1"},
    )
    assert "warehouse_name = 'MUMBAI-WH1'" in sql
    assert "strict_word_similarity" not in sql
