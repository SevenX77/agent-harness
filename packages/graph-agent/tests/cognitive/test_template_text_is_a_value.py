"""The cognitive template is a VALUE, and rendering it did not change.

`apply_v030_cognitive_template` used to build its output from an f-string body,
which meant the un-substituted template existed only as source code — nothing
the run could report. A prompt reader therefore could not tell "the model was
told this because the template says so" from "because the phase author wrote
it", which is the very distinction the template id was introduced for
(`V030_COGNITIVE_TEMPLATE_ID`'s docstring).

Extracting the body into a module constant rendered with `str.format` is a pure
refactor, and this test is what makes that claim checkable rather than asserted:
`v030_cognitive_template.golden.md` was rendered BY THE F-STRING IMPLEMENTATION
(recovered from git) with the arguments below, and the two outputs were equal
byte for byte. A future edit that shifts a single space in the boilerplate has
to say so by updating the golden.
"""

from __future__ import annotations

from pathlib import Path

from graph_agent.cognitive.prompt import (
    V030_COGNITIVE_TEMPLATE_TEXT,
    apply_v030_cognitive_template,
)

GOLDEN = Path(__file__).parent / "v030_cognitive_template.golden.md"

RENDER_ARGS = {
    "phase_name": "work",
    "role": "ROLE_TEXT",
    "goal": "GOAL_TEXT",
    "steps": [{"id": "S1", "name": "first", "content": "do it"}],
    "protocols": [{"id": "P1", "content": "obey"}],
    "output_schema": {"type": "object", "properties": {"summary": {"type": "string"}}},
    "knowledge_base_markdown": "KB_TEXT",
    "reference_registry_listing": "REF_LIST",
    "inline_examples": ["EX_ONE"],
    "example_registry_listing": "EXAMPLE_LIST",
    "role_prefix": "PREFIX_TEXT",
}


def test_the_template_is_readable_without_running_it() -> None:
    """The slots are visible in the text, which is the whole point of exposing it."""
    for slot in ("{role}", "{goal}", "{steps_md}", "{protocols_md}", "{schema_md}"):
        assert slot in V030_COGNITIVE_TEMPLATE_TEXT, slot


def test_rendering_is_unchanged_by_the_extraction() -> None:
    rendered = apply_v030_cognitive_template(**RENDER_ARGS)  # type: ignore[arg-type]

    assert rendered == GOLDEN.read_text(encoding="utf-8")


def test_no_slot_survives_unsubstituted() -> None:
    """A `.format` template fails silently different from an f-string: a slot
    the caller forgot reaches the model as literal braces instead of raising."""
    rendered = apply_v030_cognitive_template(**RENDER_ARGS)  # type: ignore[arg-type]

    for slot in ("{role}", "{goal}", "{steps_md}", "{protocols_md}", "{schema_md}",
                 "{business_data_md_shape}", "{aligned_markdown}"):
        assert slot not in rendered, slot
