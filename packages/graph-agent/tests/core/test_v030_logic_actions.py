from __future__ import annotations

from pathlib import Path

import pytest
from graph_agent.core.exceptions import GraphAgentFatalError, SkillLoadError
from graph_agent.core.graph_assembler import assemble_graph
from graph_agent.core.loader import SkillLoader


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _logic_graph(root: Path, action_name: str = "normalize") -> None:
    _write(
        root / "GRAPH.md",
        """---
schema_version: "0.3.0"
name: logic-actions
io:
  inputs:
    type: object
    properties:
      raw:
        type: string
  outputs:
    type: object
    properties:
      clean:
        type: string
phases:
  - id: normalize
    src: phases/normalize
    depends_on: []
---
""",
    )
    _write(
        root / "phases" / "normalize" / "LOGIC.md",
        f"""---
mode: logic
name: normalize
io:
  inputs:
    type: object
    properties:
      raw:
        type: string
  outputs:
    type: object
    properties:
      clean:
        type: string
actions:
  - {action_name}
---
""",
    )


def test_v030_logic_action_uses_root_level_one_hop_file(tmp_path: Path) -> None:
    _logic_graph(tmp_path)
    _write(
        tmp_path / "actions" / "normalize.py",
        "def run(state_slice, **kwargs):\n"
        "    return {'clean': state_slice['raw'].strip().lower()}\n",
    )

    compiled = SkillLoader().compile_skill(tmp_path)
    graph = assemble_graph(compiled).graph
    result = graph.invoke({"data": {"raw": "  HELLO  "}, "flow": {}, "messages": []})

    assert result["data"]["clean"] == "hello"


def test_v030_logic_action_rejects_path_like_name(tmp_path: Path) -> None:
    _logic_graph(tmp_path, "../bad")

    with pytest.raises(SkillLoadError, match=r"\[F-v3-logic-action-name-invalid\]"):
        SkillLoader().compile_skill(tmp_path)


def test_v030_logic_action_return_must_be_dict(tmp_path: Path) -> None:
    _logic_graph(tmp_path)
    _write(tmp_path / "actions" / "normalize.py", "def run(state_slice, **kwargs):\n    return 1\n")
    compiled = SkillLoader().compile_skill(tmp_path)
    graph = assemble_graph(compiled).graph

    with pytest.raises(GraphAgentFatalError, match=r"\[F-v3-logic-action-return-invalid\]"):
        graph.invoke({"data": {"raw": "x"}, "flow": {}, "messages": []})
