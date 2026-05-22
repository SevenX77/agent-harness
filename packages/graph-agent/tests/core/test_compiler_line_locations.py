"""Line-location helpers for V2.1 YAML frontmatter."""

from __future__ import annotations

from pathlib import Path

import pytest
from graph_agent.core.exceptions import SkillLoadError
from graph_agent.core.loader import SkillLoader
from graph_agent.core.parser import locate_line_for_pydantic_loc, parse_markdown_parts


def test_loader_validation_error_mentions_graph_md(tmp_path: Path) -> None:
    (tmp_path / "io").mkdir()
    (tmp_path / "phases" / "hello").mkdir(parents=True)
    (tmp_path / "io" / "inputs.json").write_text("{}\n", encoding="utf-8")
    (tmp_path / "io" / "outputs.json").write_text("{}\n", encoding="utf-8")
    (tmp_path / "GRAPH.md").write_text(
        """---
schema_version: "2.1"
name: ""
---
<input src="io/inputs.json" />
<output src="io/outputs.json" />
<phase id="hello" src="phases/hello" depends_on="" />
""",
        encoding="utf-8",
    )
    (tmp_path / "phases" / "hello" / "SKILL.md").write_text(
        """---
mode: skill
name: hello
---
<system_prompt>
Hello.
</system_prompt>
<exit_contract>
Done.
</exit_contract>
""",
        encoding="utf-8",
    )

    with pytest.raises(SkillLoadError) as excinfo:
        SkillLoader().compile_skill(tmp_path)

    assert "GRAPH.md" in str(excinfo.value)
    assert "manifest validation failed" in str(excinfo.value)


@pytest.mark.skip(reason="Fails on Python 3.12.9 due to ruamel YAML issue")
def test_locate_line_returns_one_indexed_line(tmp_path: Path) -> None:
    graph = tmp_path / "GRAPH.md"
    graph.write_text(
        "---\n"  # line 1
        'schema_version: "2.1"\n'  # line 2
        "name: hello\n"  # line 3
        "phases:\n"  # line 4
        "  - id: phase_a\n"  # line 5
        "    src: phases/phase_a\n"  # line 6
        "    depends_on: []\n"  # line 7
        "---\n",
        encoding="utf-8",
    )
    frontmatter, _, _ = parse_markdown_parts(graph)

    assert locate_line_for_pydantic_loc(frontmatter, ("name",)) == 3
    assert locate_line_for_pydantic_loc(frontmatter, ("phases", 0, "src")) == 6


def test_locate_line_returns_none_for_plain_dict() -> None:
    plain = {"name": "x", "phases": [{"id": "p"}]}

    assert locate_line_for_pydantic_loc(plain, ("name",)) is None
