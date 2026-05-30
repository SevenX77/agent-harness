"""Red tests for public run_skill entrypoint root-shape failures."""

from __future__ import annotations

from pathlib import Path

from graph_agent.core.runner import run_skill


def test_run_skill_single_markdown_file_returns_v030_root_error(
    tmp_path: Path, mock_skill_resolver: object
) -> None:
    skill_file = tmp_path / "ordinary.md"
    skill_file.write_text("# ordinary markdown\n", encoding="utf-8")

    result = run_skill(skill_file, skill_resolver=mock_skill_resolver)

    assert result.success is False
    assert result.context == {}
    assert result.error is not None
    assert result.error.code == "[F-v3-graph-root-missing]"


def test_run_skill_single_skill_md_file_returns_v030_root_error(
    tmp_path: Path, mock_skill_resolver: object
) -> None:
    skill_file = tmp_path / "SKILL.md"
    skill_file.write_text(
        """---
schema_version: "2.0"
name: legacy
type: agent
---
""",
        encoding="utf-8",
    )

    result = run_skill(skill_file, skill_resolver=mock_skill_resolver)

    assert result.success is False
    assert result.context == {}
    assert result.error is not None
    assert result.error.code == "[F-v3-graph-root-missing]"
