"""Builtin reference reader used during V0.3.0 prompt assembly."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ReferenceReaderInput:
    skill_id: str
    phase_id: str
    references: list[dict[str, str]]
    max_output_tokens: int = 3000
    language: str = "zh"


@dataclass(frozen=True)
class ReferenceReaderOutput:
    markdown: str
    used_reference_ids: list[str]
    warnings: list[str] = field(default_factory=list)


def read_references_for_prompt(payload: ReferenceReaderInput) -> ReferenceReaderOutput:
    """Produce deterministic assembly-time knowledge markdown for references."""

    if not payload.skill_id or not payload.phase_id:
        raise ValueError("[F-v3-reference-reader-input-invalid] skill_id/phase_id required")
    if payload.max_output_tokens < 500 or payload.max_output_tokens > 12000:
        raise ValueError("[F-v3-reference-reader-input-invalid] max_output_tokens out of range")

    sections: list[str] = []
    used_ids: list[str] = []
    for item in payload.references:
        ref_id = str(item.get("id") or "").strip()
        summary = str(item.get("summary") or "").strip()
        content = str(item.get("content") or "").strip()
        if not ref_id:
            raise ValueError("[F-v3-reference-reader-input-invalid] reference id required")
        if not content:
            continue
        used_ids.append(ref_id)
        excerpt = _truncate_tokens(content, payload.max_output_tokens)
        sections.append(f"## {ref_id}: {summary or ref_id}\n\n{excerpt}")

    markdown = "\n\n".join(sections).strip()
    if not markdown:
        markdown = "无注册 Reference"
    return ReferenceReaderOutput(markdown=markdown, used_reference_ids=used_ids)


def fallback_reference_markdown(
    references: list[dict[str, str]],
    *,
    max_output_tokens: int = 3000,
) -> str:
    sections = [
        "> WARN [F-v3-reference-reader-failed]: builtin reference reader failed; "
        "using raw excerpt fallback."
    ]
    for item in references:
        ref_id = str(item.get("id") or "").strip()
        summary = str(item.get("summary") or "").strip()
        content = str(item.get("content") or "")
        sections.append(
            f"## {ref_id}: {summary}\n\n{_truncate_tokens(content, max_output_tokens)}".rstrip()
        )
    return "\n\n".join(sections).strip()


def output_from_any(value: Any) -> ReferenceReaderOutput:
    if isinstance(value, ReferenceReaderOutput):
        return value
    if isinstance(value, dict):
        markdown = value.get("markdown")
        used_reference_ids = value.get("used_reference_ids", [])
        warnings = value.get("warnings", [])
        if not isinstance(markdown, str) or not markdown.strip():
            raise ValueError("[F-v3-reference-reader-output-invalid] markdown required")
        if not isinstance(used_reference_ids, list) or not all(
            isinstance(item, str) for item in used_reference_ids
        ):
            raise ValueError("[F-v3-reference-reader-output-invalid] used_reference_ids invalid")
        if not isinstance(warnings, list) or not all(isinstance(item, str) for item in warnings):
            warnings = []
        return ReferenceReaderOutput(
            markdown=markdown,
            used_reference_ids=used_reference_ids,
            warnings=warnings,
        )
    raise ValueError("[F-v3-reference-reader-output-invalid] unsupported output")


def _truncate_tokens(text: str, max_tokens: int) -> str:
    words = text.split()
    if len(words) <= max_tokens:
        return text
    return " ".join(words[:max_tokens])


__all__ = [
    "ReferenceReaderInput",
    "ReferenceReaderOutput",
    "fallback_reference_markdown",
    "output_from_any",
    "read_references_for_prompt",
]
