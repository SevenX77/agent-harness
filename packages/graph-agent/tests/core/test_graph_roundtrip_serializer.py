from __future__ import annotations

import re

from graph_agent.core.graph_serializer import serialize_graph_topology
from graph_agent.core.manifest import GraphPhaseRef, PhaseIOSchema


def _ref(phase_id: str, depends_on: list[str]) -> GraphPhaseRef:
    return GraphPhaseRef(id=phase_id, src=f"phases/{phase_id}", depends_on=depends_on)


_IO = PhaseIOSchema(
    inputs={"type": "object", "properties": {}},
    outputs={"type": "object", "properties": {}},
)


def _serialize_with_original(original_md: str) -> str:
    return serialize_graph_topology(
        name="roundtrip",
        description=None,
        io=_IO,
        phases=[
            _ref("draft", ["input"]),
            _ref("review", ["draft"]),
        ],
        original_md=original_md,
    )


def test_topology_roundtrip_preserves_non_topology_graph_markdown() -> None:
    original_md = """---
# keep the file-level author note
schema_version: "v0.3.0"
name: research-pipeline
description: Research pipeline
x-studio:
  viewport:
    zoom: 0.8
metadata:
  owner: studio
iterate:
  mode: batch
  over: $.items
  item_var: item
io:
  inputs:
    type: object
    properties:
      items:
        type: array
        items:
          type: object
      topic:
        type: string
    required: [items, topic]
    additionalProperties: false
  outputs:
    type: object
    properties:
      report:
        type: string
      citations:
        type: array
        items:
          type: string
    required: [report]
phases:
  - draft
  - review
---
Intro prose that Studio must not own.
<!-- keep: intro comment -->

<phase depends_on="input">draft</phase>

Notes between old phase tags should survive.
<note>Preserve this unknown body block.</note>

<phase depends_on="draft" output>review</phase>

<!-- keep: trailing comment -->
"""

    markdown = serialize_graph_topology(
        name="research-pipeline",
        description="Research pipeline",
        io=PhaseIOSchema(
            inputs={"type": "object", "properties": {"ignored": {"type": "string"}}},
            outputs={"type": "object", "properties": {"ignored": {"type": "string"}}},
        ),
        phases=[
            _ref("draft", ["input"]),
            _ref("enrich", ["draft"]),
            _ref("review", ["enrich"]),
        ],
        original_md=original_md,
    )

    assert "# keep the file-level author note" in markdown
    assert "x-studio:" in markdown
    assert "metadata:" in markdown
    assert "iterate:" in markdown
    assert "required: [items, topic]" in markdown
    assert "Intro prose that Studio must not own." in markdown
    assert "<!-- keep: intro comment -->" in markdown
    assert "Notes between old phase tags should survive." in markdown
    assert "<note>Preserve this unknown body block.</note>" in markdown
    assert "<!-- keep: trailing comment -->" in markdown
    assert "  - draft" in markdown
    assert "  - enrich" in markdown
    assert "  - review" in markdown
    assert '<phase depends_on="input">draft</phase>' in markdown
    assert '<phase depends_on="draft">enrich</phase>' in markdown
    assert '<phase depends_on="enrich" output>review</phase>' in markdown
    assert '<phase depends_on="draft" output>review</phase>' not in markdown


def test_roundtrip_replaces_block_phases_without_deleting_following_unknown_fields() -> None:
    original_md = """---
schema_version: "v0.3.0"
name: roundtrip
phases:
  - draft
x-studio:
  viewport:
    zoom: 0.8
metadata:
  owner: studio
---
<phase depends_on="input" output>draft</phase>
"""

    markdown = _serialize_with_original(original_md)

    assert "x-studio:" in markdown
    assert "metadata:" in markdown
    assert "  owner: studio" in markdown
    assert markdown.count("\nphases:") == 1
    assert "  - draft" in markdown
    assert "  - review" in markdown


def test_roundtrip_replaces_flow_style_phases_instead_of_appending_duplicate_key() -> None:
    original_md = """---
schema_version: "v0.3.0"
name: roundtrip
phases: [draft]
x-studio:
  viewport:
    zoom: 0.8
---
<phase depends_on="input" output>draft</phase>
"""

    markdown = _serialize_with_original(original_md)

    assert "phases: [draft]" not in markdown
    assert markdown.count("\nphases:") == 1
    assert "x-studio:" in markdown
    assert "  - draft" in markdown
    assert "  - review" in markdown


def test_roundtrip_replaces_empty_flow_style_phases_without_duplicate_key() -> None:
    original_md = """---
schema_version: "v0.3.0"
name: roundtrip
phases: []
metadata:
  owner: studio
---
"""

    markdown = _serialize_with_original(original_md)

    assert "phases: []" not in markdown
    assert markdown.count("\nphases:") == 1
    assert "metadata:" in markdown
    assert "  - draft" in markdown
    assert "  - review" in markdown


def test_roundtrip_replaces_empty_block_phases_without_deleting_following_key() -> None:
    original_md = """---
schema_version: "v0.3.0"
name: roundtrip
phases:
metadata:
  owner: studio
---
"""

    markdown = _serialize_with_original(original_md)

    assert markdown.count("\nphases:") == 1
    assert "metadata:" in markdown
    assert "  owner: studio" in markdown
    assert "  - draft" in markdown
    assert "  - review" in markdown


def test_roundtrip_replaces_crlf_body_phase_tags_without_duplicates() -> None:
    original_md = (
        "---\r\n"
        'schema_version: "v0.3.0"\r\n'
        "name: roundtrip\r\n"
        "phases:\r\n"
        "  - draft\r\n"
        "---\r\n"
        "Intro text.\r\n"
        '<phase depends_on="input" output>draft</phase>\r\n'
        "Tail text.\r\n"
    )

    markdown = _serialize_with_original(original_md)

    assert markdown.count("<phase") == 2
    assert '<phase depends_on="input">draft</phase>' in markdown
    assert '<phase depends_on="draft" output>review</phase>' in markdown
    assert '<phase depends_on="input" output>draft</phase>' not in markdown
    assert "Intro text." in markdown
    assert "Tail text." in markdown


def test_roundtrip_replaces_case_insensitive_body_phase_tags_without_duplicates() -> None:
    original_md = """---
schema_version: "v0.3.0"
name: roundtrip
phases:
  - draft
---
Intro text.
<Phase depends_on="input" output>draft</Phase>
Tail text.
"""

    markdown = _serialize_with_original(original_md)

    assert len(re.findall(r"<phase\b", markdown, flags=re.IGNORECASE)) == 2
    assert "<Phase" not in markdown
    assert '<phase depends_on="input">draft</phase>' in markdown
    assert '<phase depends_on="draft" output>review</phase>' in markdown


def test_roundtrip_replaces_inline_and_commented_body_phase_tags_without_duplicates() -> None:
    original_md = """---
schema_version: "v0.3.0"
name: roundtrip
phases:
  - draft
---
Before <phase depends_on="input" output>draft</phase> after.
<phase depends_on="input" output>draft</phase> <!-- keep topology note -->
"""

    markdown = _serialize_with_original(original_md)

    assert markdown.count("<phase") == 2
    assert '<phase depends_on="input">draft</phase>' in markdown
    assert '<phase depends_on="draft" output>review</phase>' in markdown
    assert '<phase depends_on="input" output>draft</phase>' not in markdown
    assert "Before " in markdown
    assert " after." in markdown
    assert "<!-- keep topology note -->" in markdown
