"""V0.3 schema_version rejection tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from graph_agent.core.compiler import compile_skill
from graph_agent.core.exceptions import SkillLoadError
from graph_agent.core.loader import SkillLoader


def _write_v030_skill(root: Path, schema_version_literal: str) -> None:
    (root / "phases" / "hello").mkdir(parents=True)
    (root / "GRAPH.md").write_text(
        f"""---
schema_version: {schema_version_literal}
name: x
io:
  inputs:
    type: object
    properties: {{}}
  outputs:
    type: object
    properties: {{}}
phases:
  - hello
---
<phase depends_on="input" output>hello</phase>
""",
        encoding="utf-8",
    )
    (root / "phases" / "hello" / "SKILL.md").write_text(
        """---
io:
  inputs:
    type: object
    properties: {}
  outputs:
    type: object
    properties: {}
---
<role>
Say hello.
</role>
<goal>
Call finish_task.
</goal>
""",
        encoding="utf-8",
    )


def test_quoted_v0_3_0_parses_as_valid_v030_root(
    tmp_path: Path, mock_skill_resolver: object
) -> None:
    _write_v030_skill(tmp_path, '"v0.3.0"')

    compiled = compile_skill(tmp_path, cache=False, skill_resolver=mock_skill_resolver)

    assert compiled.manifest.schema_version == "v0.3.0"


def test_unquoted_1_5_fatals_cleanly(tmp_path: Path, mock_skill_resolver: object) -> None:
    _write_v030_skill(tmp_path, "1.5")

    with pytest.raises(SkillLoadError) as exc_info:
        SkillLoader().compile_skill(tmp_path, skill_resolver=mock_skill_resolver)
    assert exc_info.value.payload.code == "[F-v3-graph-schema-version-mismatch]"
