"""Disambiguation payloads for chat-ready follow-up turns."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ClarificationOption(BaseModel):
    """One selectable choice shown to the user."""

    value: str = Field(
        ...,
        description="Opaque selection token for follow-up requests (not shown to end users).",
    )
    label: str = Field(
        ...,
        description="Natural-language label shown in UI or chat (no schema or column names).",
    )
    score: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Match confidence when applicable; omitted from user-facing copy.",
    )


class ClarificationPayload(BaseModel):
    """
    Returned when multiple records match a single-entity question.

    Integrators map the chosen option's ``value`` into ``resolved_filters`` using
    ``parameter`` (machine-readable only; not repeated in ``message``).
    """

    parameter: str = Field(
        ...,
        description="Internal filter key for follow-up requests (not for end-user display).",
    )
    original_phrase: str = Field(
        ...,
        description="User text that could not be matched confidently.",
    )
    options: list[ClarificationOption] = Field(default_factory=list)
    message: str = Field(
        default="",
        description="Short prompt for the user or chat UI.",
    )
