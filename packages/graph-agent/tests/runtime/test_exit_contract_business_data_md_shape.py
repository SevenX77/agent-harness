"""The exit contract must state the shape ``business_data_md`` is parsed with.

``finish_task(business_data_md=...)`` is handed to ``md_to_json``/``parse_md``,
which reads every ``## `` heading as ONE complete output object and the lines
under it as that object's fields. Telling the model only "follow output_schema"
and then dumping a JSON Schema invites the opposite reading — one heading per
FIELD — which parses as N objects each missing every field.
"""

from __future__ import annotations

import re

from pydantic import BaseModel

from graph_agent.cognitive.prompt import apply_v030_cognitive_template
from graph_agent.tools.md_to_json import parse_md

_SCHEMA = {
    "type": "object",
    "required": ["parsed_events", "event_timeline", "events_raw"],
    "properties": {
        "parsed_events": {"type": "array", "items": {"type": "object"}},
        "event_timeline": {"type": "array", "items": {"type": "object"}},
        "events_raw": {"type": "string"},
    },
}


class _Item(BaseModel):
    parsed_events: str
    event_timeline: str
    events_raw: str


def _exit_contract_of(prompt: str) -> str:
    return prompt[prompt.index("<exit_contract>") :]


def _markdown_fence_of(text: str) -> str:
    match = re.search(r"```markdown\n(.*?)```", text, re.DOTALL)
    assert match is not None, f"exit contract carries no markdown skeleton:\n{text}"
    return match.group(1)


def _build_prompt() -> str:
    return apply_v030_cognitive_template(
        phase_name="aggregate",
        role="Aggregator",
        goal="Aggregate events.",
        steps=[],
        protocols=[],
        output_schema=_SCHEMA,
    )


def test_exit_contract_says_one_heading_is_one_object_not_one_field() -> None:
    contract = _exit_contract_of(_build_prompt())

    assert "## " in contract
    for field_name in _SCHEMA["properties"]:
        assert field_name in contract


def test_the_skeleton_it_teaches_parses_as_exactly_one_complete_object() -> None:
    """Anti-drift: the taught shape must be the shape the parser accepts.

    A prose rule can drift from ``parse_md`` silently. Running the rendered
    skeleton through the real parser is what keeps the instruction honest.
    """
    skeleton = _markdown_fence_of(_exit_contract_of(_build_prompt()))

    blocks = parse_md(skeleton, _Item)

    assert len(blocks) == 1, (
        f"the taught skeleton parses as {len(blocks)} items, so it teaches the "
        f"per-field split that breaks real runs:\n{skeleton}"
    )
    assert set(blocks[0].data) == set(_SCHEMA["properties"])


def test_a_phase_without_an_output_schema_gets_no_skeleton() -> None:
    prompt = apply_v030_cognitive_template(
        phase_name="main",
        role="Researcher",
        goal="Answer.",
        steps=[],
        protocols=[],
    )

    assert "```markdown" not in _exit_contract_of(prompt)
