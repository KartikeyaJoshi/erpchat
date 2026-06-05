from app.planning.entity_extractor import extract_entity_filter


class _Response:
    def __init__(self, content: str):
        self.content = content


class _FakeLLM:
    def invoke(self, _messages):
        return _Response(
            """
            {
              "use_entity_match": true,
              "query_kind": "warehouse_stock",
              "parameter": "warehouse_name",
              "table": "inventory",
              "column": "warehouse_name",
              "phrase": "Mumbai Warehouse"
            }
            """
        )


def test_extract_entity_filter_returns_phrase_only():
    spec, usage = extract_entity_filter(
        llm=_FakeLLM(),
        user_query="What is the current stock level of Mumbai Warehouse?",
        schema_context="inventory(warehouse_name, stock_on_hand)",
        metric_definitions="",
    )
    assert spec is not None
    assert spec.phrase == "Mumbai Warehouse"
    assert spec.column == "warehouse_name"
    assert usage["llm_total_tokens"] == 0
