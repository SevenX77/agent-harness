"""MVP-3 T3 parse_skill_md pure text parsing tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from graph_agent.core.exceptions import SkillLoadError
from graph_agent.core.loader import parse_skill_md

ROOT = Path(__file__).resolve().parents[3]


def _graph_skill_yaml(phases: str) -> str:
    return (
        "---\n"
        'schema_version: "2.0"\n'
        "name: graph\n"
        "description: test graph\n"
        "type: graph\n"
        "io: {inputs: [], outputs: []}\n"
        "phases:\n"
        f"{phases}"
        "---\n"
    )


@pytest.mark.parametrize(
    "skill_path",
    [
        "skills/text-segmentation/SKILL.md",
        "skills/event-extraction/SKILL.md",
        "skills/batch-analysis/SKILL.md",
        "skills/global-synthesis/SKILL.md",
    ],
)
def test_parse_skill_md_core_skills_return_expected_top_level_keys(skill_path: str) -> None:
    raw = parse_skill_md((ROOT / skill_path).read_text(encoding="utf-8"))

    assert raw["schema_version"] == "2.0"
    assert raw["name"]
    assert raw["description"]
    assert raw["type"] == "graph"
    assert isinstance(raw["io"], dict)
    assert isinstance(raw["phases"], list)


def test_parse_skill_md_extracts_named_body_output_schema_block() -> None:
    raw = parse_skill_md(
        _graph_skill_yaml(
            "  - name: setup\n"
            "    mode: logic\n"
            "    execute_steps: [script.setup.run]\n"
            "  - name: draft\n"
            "    mode: llm\n"
        )
        + "\n"
        "## draft output_schema\n"
        "title: str\n"
        "score: int\n"
    )

    assert raw["phases"][1]["output_schema_md"] == "title: str\nscore: int"


def test_parse_skill_md_preserves_output_example_with_inner_markdown_heading() -> None:
    example = (
        '<output_example name="Item">\n'
        "## items\n"
        "- title (str, required): item title\n"
        "</output_example>"
    )

    raw = parse_skill_md(
        _graph_skill_yaml("  - name: draft\n    mode: llm\n")
        + "\n"
        "## draft output_example\n"
        f"{example}\n\n"
        "## Notes\n"
        "This is documentation, not part of the schema block.\n"
    )

    assert raw["phases"][0]["output_example_md"] == example
    assert raw["phases"][0]["output_example"] == example


def test_parse_skill_md_uses_phase_heading_context_for_schema_block() -> None:
    raw = parse_skill_md(
        _graph_skill_yaml("  - name: draft\n    mode: llm\n")
        + "\n"
        "## Phase: draft\n"
        "Phase docs.\n"
        "### Output Schema\n"
        "```yaml\n"
        "title: str\n"
        "score: int\n"
        "```\n"
    )

    assert raw["phases"][0]["output_schema_md"] == (
        "```yaml\n"
        "title: str\n"
        "score: int\n"
        "```"
    )


def test_parse_skill_md_infers_single_phase_for_unqualified_output_example() -> None:
    example = (
        '<output_example name="Summary">\n'
        "## summary\n"
        "- title (str, required): summary title\n"
        "</output_example>"
    )

    raw = parse_skill_md(
        _graph_skill_yaml("  - name: summarize\n    mode: llm\n")
        + "\n"
        "## Output Example\n"
        f"{example}\n"
    )

    assert raw["phases"][0]["output_example_md"] == example


def test_parse_skill_md_mirrors_yaml_output_example_to_md_field() -> None:
    example = (
        '<output_example name="Item">\n'
        "## items\n"
        "- title (str, required): title\n"
        "</output_example>"
    )

    raw = parse_skill_md(
        _graph_skill_yaml(
            "  - name: draft\n"
            "    mode: llm\n"
            "    output_example: |\n"
            f"      {example.replace(chr(10), chr(10) + '      ')}\n"
        )
    )

    assert raw["phases"][0]["output_example_md"].strip() == example


def test_parse_skill_md_missing_frontmatter_raises() -> None:
    with pytest.raises(SkillLoadError, match="frontmatter"):
        parse_skill_md("# not a SKILL frontmatter")


def test_parse_skill_md_duplicate_yaml_key_raises() -> None:
    with pytest.raises(SkillLoadError, match="duplicate key"):
        parse_skill_md(
            "---\n"
            "name: one\n"
            "name: two\n"
            "description: d\n"
            "type: persona\n"
            "role_profile: r\n"
            "---\n"
        )


def test_parse_skill_md_unknown_phase_in_schema_heading_raises() -> None:
    with pytest.raises(SkillLoadError, match="unknown phase"):
        parse_skill_md(
            _graph_skill_yaml("  - name: draft\n    mode: llm\n")
            + "\n"
            "## missing output_schema\n"
            "title: str\n"
        )


def test_parse_skill_md_ambiguous_schema_heading_raises() -> None:
    with pytest.raises(SkillLoadError, match="must name one phase"):
        parse_skill_md(
            _graph_skill_yaml(
                "  - name: draft\n"
                "    mode: llm\n"
                "  - name: review\n"
                "    mode: llm\n"
            )
            + "\n"
            "## output_schema\n"
            "title: str\n"
        )


def test_parse_skill_md_duplicate_markdown_schema_block_raises() -> None:
    with pytest.raises(SkillLoadError, match="Duplicate output_schema_md"):
        parse_skill_md(
            _graph_skill_yaml("  - name: draft\n    mode: llm\n")
            + "\n"
            "## draft output_schema\n"
            "title: str\n"
            "## draft output_schema\n"
            "score: int\n"
        )


def test_parse_skill_md_empty_markdown_schema_block_raises() -> None:
    with pytest.raises(SkillLoadError, match="is empty"):
        parse_skill_md(
            _graph_skill_yaml("  - name: draft\n    mode: llm\n")
            + "\n"
            "## draft output_schema\n"
            "## Notes\n"
            "not schema\n"
        )
