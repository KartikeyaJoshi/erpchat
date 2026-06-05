"""Contract model tests."""

from app.contracts.errors import ErrorCode, ErrorDetail
from app.contracts.planner import PlannerOutput
from app.contracts.responses import QueryResponse, ValidationSummary


def test_planner_output_parses():
    raw = (
        '{"category": "DIRECT_QUERY", "query_mode": "SINGLE", "targets": [], '
        '"steps": ["Step 1: list orders"]}'
    )
    plan = PlannerOutput.model_validate_json(raw)
    assert plan.category == "DIRECT_QUERY"
    assert plan.query_mode == "SINGLE"
    assert len(plan.steps) == 1


def test_planner_multi_step_parses():
    raw = """
    {
      "category": "COMPLEX_ANALYSIS",
      "query_mode": "MULTI_STEP",
      "targets": [
        {
          "id": "credit_parties",
          "label": "Credit check",
          "tables": ["customers"],
          "intent": "List high credit customers with balance"
        }
      ],
      "steps": ["Step 1"]
    }
    """
    plan = PlannerOutput.model_validate_json(raw)
    assert plan.query_mode == "MULTI_STEP"
    assert plan.targets[0].id == "credit_parties"


def test_query_response_shape():
    resp = QueryResponse(
        status="success",
        trace_id="abc-123",
        query_mode="MULTI_STEP",
        insight="Revenue is 100.00",
        validation=ValidationSummary(passed=True),
    )
    assert resp.trace_id == "abc-123"
    assert resp.query_mode == "MULTI_STEP"
    assert resp.validation.passed is True


def test_error_detail_codes():
    err = ErrorDetail(code=ErrorCode.SQL_VALIDATION, message="bad join")
    assert err.code == ErrorCode.SQL_VALIDATION
