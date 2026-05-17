"""V2.1 tool/action path containment tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from graph_agent.core.exceptions import SkillLoadError
from graph_agent.core.loader import SkillLoader


def _write_minimal_graph(root: Path, action_body: str) -> None:
    (root / "io").mkdir(parents=True)
    (root / "phases" / "prepare" / "actions").mkdir(parents=True)
    (root / "io" / "inputs.json").write_text("{}\n", encoding="utf-8")
    (root / "io" / "outputs.json").write_text("{}\n", encoding="utf-8")
    (root / "GRAPH.md").write_text(
        """---
schema_version: "2.1"
name: action-path-test
---
<input src="io/inputs.json" />
<output src="io/outputs.json" />
<phase id="prepare" src="phases/prepare" depends_on="" />
""",
        encoding="utf-8",
    )
    (root / "phases" / "prepare" / "LOGIC.md").write_text(
        """---
mode: logic
name: prepare
---
<python_callable>
prepare
</python_callable>
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

    with pytest.raises(SkillLoadError, match="F-v21-purity"):
        SkillLoader().compile_skill(tmp_path)


def test_root_level_actions_directory_is_rejected(tmp_path: Path) -> None:
    _write_minimal_graph(tmp_path, "def prepare(context):\n    return {}\n")
    (tmp_path / "actions").mkdir()

    with pytest.raises(SkillLoadError, match="root-level actions/ is not allowed"):
        SkillLoader().compile_skill(tmp_path)
