"""
strict_word_similarity match bands and disambiguation helpers.

Used after SQL returns rows that include a match_score column.
No entity catalog — the caller supplies parameter name and user phrase.

Score bands:
  >= 0.8  excellent  → auto proceed, silent
  0.4–0.79 fair     → proceed with entity_match_notes disclaimer
  < 0.4   poor      → needs_clarification, do not treat as final answer
  ambiguous fair    → two+ rows within ENTITY_MATCH_AMBIGUITY_GAP → clarify
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from app import config


class MatchBand(str, Enum):
    EXCELLENT = "excellent"
    FAIR = "fair"
    POOR = "poor"
    AMBIGUOUS = "ambiguous"
    RESOLVED = "resolved"  # client supplied exact filter on follow-up turn


@dataclass(frozen=True)
class MatchCandidate:
    value: str
    score: float
    label: str | None = None

    @property
    def display_label(self) -> str:
        return self.label or self.value


@dataclass(frozen=True)
class MatchEvaluation:
    band: MatchBand
    chosen: MatchCandidate | None
    candidates: tuple[MatchCandidate, ...]
    fair_match_note: str | None = None
    clarification_message: str | None = None

    @property
    def should_clarify(self) -> bool:
        return self.band in (MatchBand.POOR, MatchBand.AMBIGUOUS)

    @property
    def can_proceed(self) -> bool:
        return self.band in (MatchBand.EXCELLENT, MatchBand.FAIR, MatchBand.RESOLVED)


def classify_score(score: float) -> MatchBand:
    if score >= config.ENTITY_MATCH_EXCELLENT_MIN:
        return MatchBand.EXCELLENT
    if score >= config.ENTITY_MATCH_FAIR_MIN:
        return MatchBand.FAIR
    return MatchBand.POOR


def build_fair_match_note(
    canonical_value: str,
    original_phrase: str,
    *,
    parameter: str | None = None,
) -> str:
    suffix = f" ({parameter})" if parameter else ""
    return (
        f"Showing results for {canonical_value}{suffix} "
        f"(matched from '{original_phrase}')."
    )


def _parse_score(raw: Any) -> float | None:
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def extract_candidates_from_rows(
    rows: list[dict[str, Any]],
    *,
    value_column: str,
    score_column: str | None = None,
) -> list[MatchCandidate]:
    """Build ranked candidates from SQL rows that include match_score."""
    score_key = score_column or config.ENTITY_MATCH_SCORE_COLUMN
    seen: dict[str, MatchCandidate] = {}

    for row in rows:
        value = row.get(value_column)
        if value is None or str(value).strip() == "":
            continue
        text = str(value).strip()
        score = _parse_score(row.get(score_key))
        if score is None:
            continue
        existing = seen.get(text)
        if existing is None or score > existing.score:
            seen[text] = MatchCandidate(value=text, score=score, label=text)

    return sorted(seen.values(), key=lambda c: c.score, reverse=True)


def _is_ambiguous(candidates: list[MatchCandidate]) -> bool:
    fair = [c for c in candidates if c.score >= config.ENTITY_MATCH_FAIR_MIN]
    if len(fair) < 2:
        return False
    return (fair[0].score - fair[1].score) < config.ENTITY_MATCH_AMBIGUITY_GAP


def evaluate_matches(
    candidates: list[MatchCandidate],
    *,
    original_phrase: str,
    parameter: str,
    already_resolved: bool = False,
) -> MatchEvaluation:
    """
    Apply score bands to ranked candidates.

    already_resolved: True when client sent resolved_filters on a follow-up turn.
    """
    if already_resolved and candidates:
        chosen = candidates[0]
        return MatchEvaluation(
            band=MatchBand.RESOLVED,
            chosen=chosen,
            candidates=tuple(candidates),
        )

    if not candidates:
        return MatchEvaluation(
            band=MatchBand.POOR,
            chosen=None,
            candidates=(),
            clarification_message=(
                f"No confident match for '{original_phrase}' on {parameter}. "
                "Please choose a value or rephrase."
            ),
        )

    if _is_ambiguous(candidates):
        return MatchEvaluation(
            band=MatchBand.AMBIGUOUS,
            chosen=None,
            candidates=tuple(candidates[: config.ENTITY_MATCH_CANDIDATE_LIMIT]),
            clarification_message=(
                f"Multiple values match '{original_phrase}'. Please select one."
            ),
        )

    top = candidates[0]
    band = classify_score(top.score)

    if band == MatchBand.POOR:
        return MatchEvaluation(
            band=MatchBand.POOR,
            chosen=None,
            candidates=tuple(candidates[: config.ENTITY_MATCH_CANDIDATE_LIMIT]),
            clarification_message=(
                f"Could not confidently match '{original_phrase}' on {parameter}. "
                "Please choose from the options below."
            ),
        )

    note = None
    if band == MatchBand.FAIR:
        note = build_fair_match_note(top.value, original_phrase, parameter=parameter)

    return MatchEvaluation(
        band=band,
        chosen=top,
        candidates=tuple(candidates),
        fair_match_note=note,
    )


def evaluate_rows(
    rows: list[dict[str, Any]],
    *,
    value_column: str,
    original_phrase: str,
    parameter: str,
    already_resolved: bool = False,
    score_column: str | None = None,
) -> MatchEvaluation:
    """Convenience: extract candidates from rows then evaluate bands."""
    candidates = extract_candidates_from_rows(
        rows,
        value_column=value_column,
        score_column=score_column,
    )
    return evaluate_matches(
        candidates,
        original_phrase=original_phrase,
        parameter=parameter,
        already_resolved=already_resolved,
    )
