"""API request contracts."""

from pydantic import BaseModel, ConfigDict, Field


class QueryRequest(BaseModel):
    """
    Public analyze request body.

    Only ``query`` appears in OpenAPI/Swagger. Clients may still send
    ``resolved_filters`` on clarification follow-ups; it is accepted but not
    documented in the public schema.
    """

    model_config = ConfigDict(
        extra="allow",
        json_schema_extra={
            "examples": [{"query": "What is total revenue in 2026?"}],
        },
    )

    query: str = Field(
        ...,
        description="Natural-language business question.",
    )


def resolved_filters_from_request(payload: QueryRequest) -> dict[str, str]:
    """Extract optional clarification follow-up filters from extra request fields."""
    extras = getattr(payload, "__pydantic_extra__", None) or {}
    raw = extras.get("resolved_filters")
    if not isinstance(raw, dict):
        return {}
    return {str(k): str(v) for k, v in raw.items()}
