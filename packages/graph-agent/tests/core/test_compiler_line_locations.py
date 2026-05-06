"""Cohesion plan 方针 3.1 + 3.2 (2026-04-26): the parser uses ruamel.yaml
in round-trip mode so the returned mapping carries per-key line/column
metadata, and ``compile_skill`` translates Pydantic ``loc`` tuples into
concrete SKILL.md line numbers in the ``CompileIssue.location`` string.

Studio's UI gates "click error → jump to file line" on this format;
locking it down with regression tests keeps the contract stable.
"""
from __future__ import annotations

import re
from pathlib import Path

from graph_agent.core.compiler import compile_skill
from graph_agent.core.parser import locate_line_for_pydantic_loc, parse_skill_file


def test_compile_issue_carries_concrete_line_number(tmp_path: Path) -> None:
    """A field-level Pydantic error must produce a
    ``SKILL.md:<line>:<dotted-loc>`` location string."""
    skill = tmp_path / "SKILL.md"
    skill.write_text(
        "---\n"  # line 1
        'schema_version: "2.0"\n'  # line 2
        "name: bad\n"  # line 3
        "description: x\n"  # line 4
        "type: graph\n"  # line 5
        "io:\n"  # line 6
        "  inputs: []\n"  # line 7
        "  outputs: []\n"  # line 8
        "phases:\n"  # line 9
        "  - mode: llm\n"  # line 10
        "    name: \"\"\n"  # line 11 — empty string fails min_length=1
        "    prompt: hi\n"  # line 12
        "---\n",
        encoding="utf-8",
    )

    result = compile_skill(skill)
    assert not result.passed
    locations = [f.location for f in result.fatals]

    # Expect at least one location of the form SKILL.md:<digits>:phases.0.name
    matched = [
        loc for loc in locations
        if re.match(r"^SKILL\.md:\d+:.*\.phases\.0(\..*)?\.name$", loc)
        or re.match(r"^SKILL\.md:\d+:phases\.0(\..*)?\.name$", loc)
    ]
    assert matched, (
        "Compile fatal for an empty phase name must include the file "
        "line number for phases[0].name. Got locations: "
        f"{locations}"
    )


def test_locate_line_returns_one_indexed_line(tmp_path: Path) -> None:
    """``locate_line_for_pydantic_loc`` walks the parsed frontmatter
    and returns 1-indexed line numbers consistent with the file."""
    skill = tmp_path / "SKILL.md"
    skill.write_text(
        "---\n"  # line 1
        'schema_version: "2.0"\n'  # line 2
        "name: hello\n"  # line 3
        "description: x\n"  # line 4
        "type: graph\n"  # line 5
        "io: {inputs: [], outputs: []}\n"  # line 6
        "phases:\n"  # line 7
        "  - mode: llm\n"  # line 8 — first list item begins here
        "    name: phase_a\n"  # line 9
        "    prompt: hi\n"  # line 10
        "---\n",
        encoding="utf-8",
    )
    parsed = parse_skill_file(skill)
    fm = parsed["frontmatter"]

    # Top-level field: 'name' is on line 3
    line_name = locate_line_for_pydantic_loc(fm, ("name",))
    assert line_name == 3, f"expected line 3 for 'name', got {line_name}"

    # Nested-list field: phases[0].name is on line 9
    line_phase_name = locate_line_for_pydantic_loc(fm, ("phases", 0, "name"))
    assert line_phase_name == 9, (
        f"expected line 9 for 'phases.0.name', got {line_phase_name}"
    )


def test_locate_line_returns_none_for_unknown_path() -> None:
    """Plain-dict input has no line metadata; the helper must return
    None rather than crash."""
    plain = {"name": "x", "phases": [{"mode": "llm", "name": "p"}]}
    assert locate_line_for_pydantic_loc(plain, ("name",)) is None
