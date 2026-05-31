"""Predict trace exporter utilities."""

from __future__ import annotations

from typing import Any, Literal, cast

from graph_agent.core.result import PhaseRecord

_USAGE_KEYS = {
    "usage",
    "token_usage",
    "input_tokens",
    "output_tokens",
    "total_tokens",
    "prompt_tokens",
    "completion_tokens",
    "total_cost",
    "cost",
}

_MOCKED_SOURCES = {"golden_case", "copilot", "heuristic_stub", "manual"}


def assemble_phase_record(
    raw_phase: dict[str, Any],
    *,
    max_field_chars: int = 4096,
) -> PhaseRecord:
    """Convert a raw trace phase/event into a compact Predict business slice."""

    mocked_source = _mocked_source(raw_phase.get("mocked_source"))
    return PhaseRecord(
        phase_name=str(raw_phase.get("phase_name") or raw_phase.get("name") or ""),
        type=_phase_type(raw_phase, mocked_source),
        inputs=_sanitize_mapping(raw_phase.get("inputs", {}), max_field_chars=max_field_chars),
        outputs=_sanitize_mapping(raw_phase.get("outputs", {}), max_field_chars=max_field_chars),
        mocked_source=mocked_source,
    )


def assemble_phase_records(
    raw_phases: list[dict[str, Any]],
    *,
    max_field_chars: int = 4096,
) -> list[PhaseRecord]:
    """Convert a list of raw trace phase/event payloads to PhaseRecord objects."""

    return [
        assemble_phase_record(raw_phase, max_field_chars=max_field_chars)
        for raw_phase in raw_phases
    ]


def _phase_type(
    raw_phase: dict[str, Any],
    mocked_source: Literal["golden_case", "copilot", "heuristic_stub", "manual"] | None,
) -> Literal["logic", "llm"]:
    raw_type = raw_phase.get("type")
    if raw_type in {"logic", "llm"}:
        return cast(Literal["logic", "llm"], raw_type)
    if mocked_source is not None:
        return "llm"
    return "logic"


def _mocked_source(
    value: Any,
) -> Literal["golden_case", "copilot", "heuristic_stub", "manual"] | None:
    if value not in _MOCKED_SOURCES:
        return None
    return cast(Literal["golden_case", "copilot", "heuristic_stub", "manual"], value)


def _sanitize_mapping(value: Any, *, max_field_chars: int) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    cleaned: dict[str, Any] = {}
    truncated_fields: list[str] = []
    for key, item in value.items():
        if key in _USAGE_KEYS:
            continue
        cleaned_value, was_truncated = _truncate_value(item, max_field_chars=max_field_chars)
        cleaned[key] = cleaned_value
        if was_truncated:
            truncated_fields.append(str(key))
    if truncated_fields:
        cleaned["truncated"] = True
        cleaned["truncated_fields"] = truncated_fields
    return cleaned


def _truncate_value(value: Any, *, max_field_chars: int) -> tuple[Any, bool]:
    if isinstance(value, str):
        if len(value) > max_field_chars:
            return value[:max_field_chars], True
        return value, False
    if isinstance(value, dict):
        nested = _sanitize_mapping(value, max_field_chars=max_field_chars)
        return nested, bool(nested.get("truncated"))
    if isinstance(value, list):
        truncated = False
        items: list[Any] = []
        for item in value:
            cleaned, item_truncated = _truncate_value(item, max_field_chars=max_field_chars)
            items.append(cleaned)
            truncated = truncated or item_truncated
        return items, truncated
    return value, False


__all__ = ["assemble_phase_record", "assemble_phase_records"]
