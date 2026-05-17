"""V2.1 schema_version coercion and rejection tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from graph_agent.core.compiler import compile_skill
from graph_agent.core.exceptions import SkillLoadError
from graph_agent.core.loader import SkillLoader


def _write_v21_skill(root: Path, schema_version_literal: str) -> None:
    (root / "io").mkdir(parents=True)
    (root / "phases" / "hello").mkdir(parents=True)
    (root / "io" / "inputs.json").write_text("{}\n", encoding="utf-8")
    (root / "io" / "outputs.json").write_text("{}\n", encoding="utf-8")
    (root / "GRAPH.md").write_text(
        f"""---
schema_version: {schema_version_literal}
name: x
---
<input src="io/inputs.json" />
<output src="io/outputs.json" />
<phase id="hello" src="phases/hello" depends_on="" />
""",
        encoding="utf-8",
    )
    (root / "phases" / "hello" / "SKILL.md").write_text(
        """---
mode: skill
name: hello
---
<system_prompt>
Say hello.
</system_prompt>
<exit_contract>
Call finish_task.
</exit_contract>
""",
        encoding="utf-8",
    )


def test_unquoted_2_1_parses_as_valid_v21_root(tmp_path: Path) -> None:
    _write_v21_skill(tmp_path, "2.1")

    compiled = compile_skill(tmp_path, cache=False)

    assert compiled.manifest.schema_version == "2.1"


def test_unquoted_1_5_fatals_cleanly(tmp_path: Path) -> None:
    _write_v21_skill(tmp_path, "1.5")

    with pytest.raises(SkillLoadError, match="GRAPH.md manifest validation failed"):
        SkillLoader().compile_skill(tmp_path)
