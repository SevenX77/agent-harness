"""V0.3 tool/action path containment tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from graph_agent.core.exceptions import SkillLoadError
from graph_agent.core.loader import SkillLoader


def _write_minimal_graph(root: Path, action_body: str) -> None:
    (root / "phases" / "prepare" / "actions").mkdir(parents=True)
    (root / "GRAPH.md").write_text(
        """---
schema_version: "v0.3.0"
name: action-path-test
io:
  inputs:
    type: object
    properties: {}
  outputs:
    type: object
    properties: {}
phases:
  - prepare
---
<phase depends_on="input" output>prepare</phase>
""",
        encoding="utf-8",
    )
    (root / "phases" / "prepare" / "LOGIC.md").write_text(
        """---
io:
  inputs:
    type: object
    properties: {}
  outputs:
    type: object
    properties: {}
---
<action>prepare</action>
""",
        encoding="utf-8",
    )
    (root / "phases" / "prepare" / "actions" / "prepare.py").write_text(
        action_body,
        encoding="utf-8",
    )


def test_in_tree_action_reference_still_loads(tmp_path: Path) -> None:
    _write_minimal_graph(tmp_path, "def prepare(context):\n    return {}\n")

    compiled = SkillLoader().compile_skill(tmp_path)

    assert "prepare" in compiled.actions.for_phase("prepare")


def test_action_local_write_fatals_as_purity_violation(tmp_path: Path) -> None:
    _write_minimal_graph(
        tmp_path,
        "def prepare(context):\n    open('out.txt', 'w').write('bad')\n    return {}\n",
    )

    with pytest.raises(SkillLoadError) as exc_info:
        SkillLoader().compile_skill(tmp_path)
    assert exc_info.value.payload.code == "[F-v3-logic-action-purity-violation]"


def test_root_level_actions_directory_is_rejected(tmp_path: Path) -> None:
    _write_minimal_graph(tmp_path, "def prepare(context):\n    return {}\n")
    (tmp_path / "actions").mkdir()

    with pytest.raises(SkillLoadError, match="root-level actions/ is not allowed"):
        SkillLoader().compile_skill(tmp_path)
