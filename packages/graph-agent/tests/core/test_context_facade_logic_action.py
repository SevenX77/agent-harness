"""Runtime coverage for LOGIC actions receiving the Context facade."""

from __future__ import annotations

from pathlib import Path

from graph_agent.core.compiler import compile_skill
from graph_agent.core.graph_assembler import assemble_graph


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _score_logic_skill(root: Path) -> None:
    _write(
        root / "GRAPH.md",
        """---
schema_version: "v0.3.0"
name: context-facade-score
io:
  inputs:
    type: object
    required: [segments]
    properties:
      segments:
        type: array
        items:
          type: object
  outputs:
    type: object
    required: [report]
    properties:
      report:
        type: string
phases:
  - score
---
<phase depends_on="input" output>score</phase>
""",
    )
    _write(
        root / "phases" / "score" / "LOGIC.md",
        """---
io:
  inputs:
    type: object
    required: [segments]
    properties:
      segments:
        type: array
        items:
          type: object
  outputs:
    type: object
    required: [report]
    properties:
      report:
        type: string
actions: [score]
validator: false
---
<action>score</action>
""",
    )
    _write(
        root / "phases" / "score" / "actions" / "score.py",
        "def score(context):\n"
        "    segments = context['segments']\n"
        "    return {'report': f'scored {len(segments)} segments'}\n",
    )


def test_logic_action_can_read_context_with_item_access(
    tmp_path: Path, mock_skill_resolver: object
) -> None:
    _score_logic_skill(tmp_path)
    compiled = compile_skill(tmp_path, cache=False, skill_resolver=mock_skill_resolver)

    result = assemble_graph(compiled, skill_resolver=mock_skill_resolver).graph.invoke(
        {
            "data": {"inputs": {"segments": [{"content": "opening"}]}},
            "flow": {},
            "messages": [],
            "run_id": "r1",
        }
    )

    assert result["data"]["phase_outputs"]["score"] == {"report": "scored 1 segments"}
