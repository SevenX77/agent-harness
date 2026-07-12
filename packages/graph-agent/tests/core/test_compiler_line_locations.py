"""Line-location helpers for V2.1 YAML frontmatter."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from graph_agent.core.compiler import compile_skill
from graph_agent.core.exceptions import SkillLoadError
from graph_agent.core.loader import SkillLoader
from graph_agent.core.parser import locate_line_for_pydantic_loc, parse_markdown_parts


def _write_minimal_logic_skill(
    root: Path,
    *,
    graph_extra: str = "",
    logic_extra: str = "",
) -> None:
    (root / "phases" / "prepare" / "actions").mkdir(parents=True)
    graph_extra_block = f"{graph_extra}\n" if graph_extra else ""
    logic_extra_block = f"{logic_extra}\n" if logic_extra else ""
    (root / "GRAPH.md").write_text(
        f"""---
schema_version: "v0.3.0"
name: compiler-line-location-test
{graph_extra_block}io:
  inputs:
    type: object
    properties: {{}}
  outputs:
    type: object
    properties:
      answer:
        type: string
phases:
  - prepare
---
<phase depends_on="input" output>prepare</phase>
""",
        encoding="utf-8",
    )
    (root / "phases" / "prepare" / "LOGIC.md").write_text(
        f"""---
{logic_extra_block}io:
  inputs:
    type: object
    properties: {{}}
  outputs:
    type: object
    properties:
      answer:
        type: string
---
<action>prepare</action>
""",
        encoding="utf-8",
    )
    (root / "phases" / "prepare" / "actions" / "prepare.py").write_text(
        "def prepare(inputs):\n    return {'answer': 'ok'}\n",
        encoding="utf-8",
    )


def test_loader_validation_error_mentions_graph_md(tmp_path: Path, mock_skill_resolver: object) -> None:
    (tmp_path / "phases" / "hello").mkdir(parents=True)
    (tmp_path / "GRAPH.md").write_text(
        """---
schema_version: "v0.3.0"
name: ""
io:
  inputs:
    type: object
    properties: {}
  outputs:
    type: object
    properties: {}
phases:
  - hello
---
<phase depends_on="input" output>hello</phase>
""",
        encoding="utf-8",
    )
    (tmp_path / "phases" / "hello" / "SKILL.md").write_text(
        """---
io:
  inputs:
    type: object
    properties: {}
  outputs:
    type: object
    properties: {}
---
<role>Hello</role>
<goal>Done.</goal>
""",
        encoding="utf-8",
    )

    with pytest.raises(SkillLoadError) as excinfo:
        SkillLoader().compile_skill(tmp_path, skill_resolver=mock_skill_resolver)

    assert "GRAPH.md" in str(excinfo.value)
    # engine-compile-diagnostics-v2 §5.1: empty graph name now surfaces the revived
    # specific code instead of the generic collapsed "manifest validation failed" wrap.
    assert excinfo.value.payload is not None
    assert excinfo.value.payload.code == "[F-v3-graph-name-invalid]"


def test_graph_frontmatter_validation_payload_uses_relative_source_and_field_path(
    tmp_path: Path, mock_skill_resolver: object
) -> None:
    _write_minimal_logic_skill(tmp_path, graph_extra="unexpected_root: true")

    with pytest.raises(SkillLoadError) as excinfo:
        SkillLoader().compile_skill(tmp_path, skill_resolver=mock_skill_resolver)

    payload = excinfo.value.payload
    assert payload is not None
    assert payload.code == "[F-v3-graph-schema-unknown-field]"
    assert payload.source_path == "GRAPH.md"
    assert payload.field_path == "unexpected_root"
    assert getattr(excinfo.value, "source_path", None) == "GRAPH.md"
    assert getattr(excinfo.value, "field_path", None) == "unexpected_root"


def test_frontmatter_parse_error_payload_uses_relative_source_path(
    tmp_path: Path, mock_skill_resolver: object
) -> None:
    _write_minimal_logic_skill(tmp_path)
    (tmp_path / "GRAPH.md").write_text(
        """---
schema_version: "v0.3.0"
name: [unterminated
---
<phase depends_on="input" output>prepare</phase>
""",
        encoding="utf-8",
    )

    with pytest.raises(SkillLoadError) as excinfo:
        SkillLoader().compile_skill(tmp_path, skill_resolver=mock_skill_resolver)

    payload = excinfo.value.payload
    assert payload is not None
    assert payload.code == "[F-v3-graph-schema-unknown-field]"
    assert payload.source_path == "GRAPH.md"
    assert payload.field_path is None


def test_phase_frontmatter_validation_payload_uses_relative_source_and_field_path(
    tmp_path: Path, mock_skill_resolver: object
) -> None:
    _write_minimal_logic_skill(tmp_path, logic_extra='validator: "yes"')

    with pytest.raises(SkillLoadError) as excinfo:
        SkillLoader().compile_skill(tmp_path, skill_resolver=mock_skill_resolver)

    payload = excinfo.value.payload
    assert payload is not None
    assert payload.code == "[F-v3-logic-validator-type-invalid]"
    assert payload.source_path == "phases/prepare/LOGIC.md"
    assert payload.field_path == "validator"
    assert getattr(excinfo.value, "source_path", None) == "phases/prepare/LOGIC.md"
    assert getattr(excinfo.value, "field_path", None) == "validator"


def test_public_compile_error_payload_round_trips_location_axes(
    tmp_path: Path, mock_skill_resolver: object
) -> None:
    _write_minimal_logic_skill(tmp_path, graph_extra="unexpected_root: true")

    with pytest.raises(SkillLoadError) as excinfo:
        compile_skill(tmp_path, cache=False, skill_resolver=mock_skill_resolver)

    assert excinfo.value.payload is not None
    dumped = excinfo.value.payload.model_dump(mode="json")
    assert dumped["source_path"] == "GRAPH.md"
    assert dumped["field_path"] == "unexpected_root"
    wire_payload = getattr(excinfo.value, "error_payload", None)
    assert wire_payload is not None
    assert wire_payload["source_path"] == "GRAPH.md"
    assert wire_payload["field_path"] == "unexpected_root"


def test_locate_line_returns_one_indexed_line(tmp_path: Path, mock_skill_resolver: object) -> None:
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


# --------------------------------------------------------------------------- #
# Body-tag line attribution: role / goal / action errors must carry the        #
# FILE-absolute line of the offending tag (or the body start when the tag is   #
# entirely absent), never the hardcoded line 1 that lands on the frontmatter   #
# ``---``. The editor marks the whole file (frontmatter included), and Studio  #
# forwards the engine line verbatim, so the axis must match frontmatter errors #
# (file-absolute), not the body-relative ``_xml_line`` output.                 #
# --------------------------------------------------------------------------- #

# Fixed agent SKILL.md frontmatter: closing ``---`` on file line 10, so the
# body begins at file line 11. Keep this in lockstep with the line asserts.
_AGENT_SKILL_FRONTMATTER = """---
llm_role: analyst
io:
  inputs:
    type: object
    properties: {}
  outputs:
    type: object
    properties: {}
---
"""
_AGENT_BODY_START_LINE = 11


def _write_agent_skill(root: Path, *, body: str, phase: str = "act") -> Path:
    (root / "phases" / phase).mkdir(parents=True)
    (root / "GRAPH.md").write_text(
        f"""---
schema_version: "v0.3.0"
name: agent-line-location-test
io:
  inputs:
    type: object
    properties: {{}}
  outputs:
    type: object
    properties: {{}}
phases:
  - {phase}
---
<phase depends_on="input" output>{phase}</phase>
""",
        encoding="utf-8",
    )
    skill = root / "phases" / phase / "SKILL.md"
    skill.write_text(_AGENT_SKILL_FRONTMATTER + body, encoding="utf-8")
    return skill


def _error_line(exc: SkillLoadError, filename: str) -> int:
    match = re.search(rf"{re.escape(filename)}:(\d+)", str(exc))
    assert match is not None, f"no {filename}:<line> marker in: {exc}"
    return int(match.group(1))


def test_empty_role_tag_points_to_tag_line_not_one(
    tmp_path: Path, mock_skill_resolver: object
) -> None:
    # <goal> on file line 11, empty <role> on file line 12.
    _write_agent_skill(tmp_path, body="<goal>Done.</goal>\n<role></role>\n")

    with pytest.raises(SkillLoadError) as excinfo:
        SkillLoader().compile_skill(tmp_path, skill_resolver=mock_skill_resolver)

    assert excinfo.value.payload is not None
    assert excinfo.value.payload.code == "[F-v3-agent-role-missing]"
    assert _error_line(excinfo.value, "SKILL.md") == 12


def test_missing_role_points_to_body_start_not_one(
    tmp_path: Path, mock_skill_resolver: object
) -> None:
    _write_agent_skill(tmp_path, body="<goal>Done.</goal>\n")

    with pytest.raises(SkillLoadError) as excinfo:
        SkillLoader().compile_skill(tmp_path, skill_resolver=mock_skill_resolver)

    assert excinfo.value.payload is not None
    assert excinfo.value.payload.code == "[F-v3-agent-role-missing]"
    assert _error_line(excinfo.value, "SKILL.md") == _AGENT_BODY_START_LINE


def test_empty_goal_tag_points_to_tag_line_not_one(
    tmp_path: Path, mock_skill_resolver: object
) -> None:
    # <role> on file line 11, empty <goal> on file line 12.
    _write_agent_skill(tmp_path, body="<role>R</role>\n<goal></goal>\n")

    with pytest.raises(SkillLoadError) as excinfo:
        SkillLoader().compile_skill(tmp_path, skill_resolver=mock_skill_resolver)

    assert excinfo.value.payload is not None
    assert excinfo.value.payload.code == "[F-v3-agent-goal-missing]"
    assert _error_line(excinfo.value, "SKILL.md") == 12


def test_missing_goal_points_to_body_start_not_one(
    tmp_path: Path, mock_skill_resolver: object
) -> None:
    _write_agent_skill(tmp_path, body="<role>R</role>\n")

    with pytest.raises(SkillLoadError) as excinfo:
        SkillLoader().compile_skill(tmp_path, skill_resolver=mock_skill_resolver)

    assert excinfo.value.payload is not None
    assert excinfo.value.payload.code == "[F-v3-agent-goal-missing]"
    assert _error_line(excinfo.value, "SKILL.md") == _AGENT_BODY_START_LINE


def test_empty_action_tag_flagged_even_beside_filled_sibling(
    tmp_path: Path, mock_skill_resolver: object
) -> None:
    # Consistent with the agent's strict role/goal check: an empty <action></action>
    # is itself a diagnostic even when another action is filled. The LOGIC.md body's
    # filled action is file line 12, the empty one file line 13.
    _write_minimal_logic_skill(tmp_path)
    logic = tmp_path / "phases" / "prepare" / "LOGIC.md"
    logic.write_text(
        logic.read_text(encoding="utf-8").replace(
            "<action>prepare</action>",
            "<action>prepare</action>\n<action></action>",
        ),
        encoding="utf-8",
    )

    with pytest.raises(SkillLoadError) as excinfo:
        SkillLoader().compile_skill(tmp_path, skill_resolver=mock_skill_resolver)

    assert excinfo.value.payload is not None
    assert excinfo.value.payload.code == "[F-v3-logic-actions-empty]"
    assert _error_line(excinfo.value, "LOGIC.md") == 13


def test_unknown_body_tag_points_to_tag_file_line(
    tmp_path: Path, mock_skill_resolver: object
) -> None:
    # Sibling of role/goal: the unknown-tag diagnostic must share the file-absolute
    # axis too. role L11, goal L12, unknown <bogus> on file line 13.
    _write_agent_skill(
        tmp_path, body="<role>R</role>\n<goal>G</goal>\n<bogus>x</bogus>\n"
    )

    with pytest.raises(SkillLoadError) as excinfo:
        SkillLoader().compile_skill(tmp_path, skill_resolver=mock_skill_resolver)

    assert excinfo.value.payload is not None
    assert excinfo.value.payload.code == "[F-v3-agent-body-tag-unknown]"
    assert _error_line(excinfo.value, "SKILL.md") == 13


def test_forbidden_topology_tag_in_body_points_to_file_line(
    tmp_path: Path, mock_skill_resolver: object
) -> None:
    # scan_forbidden_topology_tags (parser) was the last body diagnostic still on
    # the body-relative axis. role L11, goal L12, forbidden <edge> on file line 13.
    _write_agent_skill(
        tmp_path, body="<role>R</role>\n<goal>G</goal>\n<edge>x</edge>\n"
    )

    with pytest.raises(SkillLoadError) as excinfo:
        SkillLoader().compile_skill(tmp_path, skill_resolver=mock_skill_resolver)

    assert "forbidden" in str(excinfo.value)
    assert _error_line(excinfo.value, "SKILL.md") == 13


def _write_graph_with_solo_phase(root: Path, *, depends_on: str) -> None:
    # GRAPH.md frontmatter closes on file line 13 → the body <phase> is on file line 14.
    (root / "GRAPH.md").write_text(
        f"""---
schema_version: "v0.3.0"
name: graph-diag-line-test
io:
  inputs:
    type: object
    properties: {{}}
  outputs:
    type: object
    properties: {{}}
phases:
  - solo
---
<phase depends_on="{depends_on}">solo</phase>
""",
        encoding="utf-8",
    )
    (root / "phases" / "solo").mkdir(parents=True)
    (root / "phases" / "solo" / "SKILL.md").write_text(
        _AGENT_SKILL_FRONTMATTER + "<role>R</role>\n<goal>G</goal>\n", encoding="utf-8"
    )


def test_graph_phase_cycle_points_to_phase_tag_file_line(
    tmp_path: Path, mock_skill_resolver: object
) -> None:
    # Regression for the auditor-found defect: the GRAPH.md <phase> diagnostics read
    # token.line_start (body-relative) and landed on line 1. They must point at the
    # <phase> tag's FILE line (14), like the sibling [F-v3-graph-phase-id-invalid].
    _write_graph_with_solo_phase(tmp_path, depends_on="solo")

    with pytest.raises(SkillLoadError) as excinfo:
        SkillLoader().compile_skill(tmp_path, skill_resolver=mock_skill_resolver)

    assert excinfo.value.payload is not None
    assert excinfo.value.payload.code == "[F-v3-graph-phase-cycle]"
    assert _error_line(excinfo.value, "GRAPH.md") == 14


def test_graph_depends_unknown_points_to_phase_tag_file_line(
    tmp_path: Path, mock_skill_resolver: object
) -> None:
    _write_graph_with_solo_phase(tmp_path, depends_on="input ghost")

    with pytest.raises(SkillLoadError) as excinfo:
        SkillLoader().compile_skill(tmp_path, skill_resolver=mock_skill_resolver)

    assert excinfo.value.payload is not None
    assert excinfo.value.payload.code == "[F-v3-graph-depends-unknown]"
    assert _error_line(excinfo.value, "GRAPH.md") == 14


def _write_graph_with_multinode_cycle(root: Path) -> None:
    # A real a->b->a cycle. GRAPH.md frontmatter closes on file line 14, so the two
    # body <phase> tags are on file lines 15 (a) and 16 (b).
    (root / "GRAPH.md").write_text(
        """---
schema_version: "v0.3.0"
name: graph-cycle-line-test
io:
  inputs:
    type: object
    properties: {}
  outputs:
    type: object
    properties: {}
phases:
  - a
  - b
---
<phase depends_on="b">a</phase>
<phase depends_on="a" output>b</phase>
""",
        encoding="utf-8",
    )
    for phase in ("a", "b"):
        (root / "phases" / phase).mkdir(parents=True)
        (root / "phases" / phase / "SKILL.md").write_text(
            _AGENT_SKILL_FRONTMATTER + "<role>R</role>\n<goal>G</goal>\n", encoding="utf-8"
        )


def test_graph_multinode_cycle_points_to_phase_tag_file_line(
    tmp_path: Path, mock_skill_resolver: object
) -> None:
    # The multi-node cycle in _validate_acyclic_graph hardcoded line 1 (the only
    # <phase> diagnostic still on the wrong axis). It must point at an offending
    # <phase> tag's FILE line (15 or 16 here), like every sibling <phase> diagnostic.
    _write_graph_with_multinode_cycle(tmp_path)

    with pytest.raises(SkillLoadError) as excinfo:
        SkillLoader().compile_skill(tmp_path, skill_resolver=mock_skill_resolver)

    assert excinfo.value.payload is not None
    assert excinfo.value.payload.code == "[F-v3-graph-phase-cycle]"
    assert "cycle detected" in str(excinfo.value)
    assert _error_line(excinfo.value, "GRAPH.md") in {15, 16}


# --------------------------------------------------------------------------- #
# Collect-all (P2): compile/lint is static analysis, not a run — one pass must  #
# surface EVERY independent diagnostic, not abort at the first. The engine      #
# carries the full set on ``exc.compile_result.issues`` (the seam Studio's      #
# compile drawer already projects); the primary ``payload`` stays the first     #
# diagnostic for the single-error (realtime-lint) consumers.                    #
# --------------------------------------------------------------------------- #


def _all_codes(exc: SkillLoadError) -> set[str]:
    compile_result = getattr(exc, "compile_result", None)
    issues = getattr(compile_result, "issues", None)
    if isinstance(issues, list) and issues:
        return {str(getattr(issue, "rule_id", "")) for issue in issues}
    return {exc.payload.code} if exc.payload is not None else set()


def test_agent_missing_role_and_goal_reported_together(
    tmp_path: Path, mock_skill_resolver: object
) -> None:
    # Body declares neither <role> nor <goal>: ONE compile must surface BOTH,
    # not abort after the role check (the core P2 regression lock).
    _write_agent_skill(tmp_path, body="Just prose, no tags.\n")

    with pytest.raises(SkillLoadError) as excinfo:
        SkillLoader().compile_skill(tmp_path, skill_resolver=mock_skill_resolver)

    codes = _all_codes(excinfo.value)
    assert "[F-v3-agent-role-missing]" in codes
    assert "[F-v3-agent-goal-missing]" in codes


def test_defects_in_separate_nodes_do_not_hide_each_other(
    tmp_path: Path, mock_skill_resolver: object
) -> None:
    # Two agent phases, each missing role+goal: one compile must surface defects
    # from BOTH files, not abort at the first node (collect-all layer 2).
    (tmp_path / "GRAPH.md").write_text(
        """---
schema_version: "v0.3.0"
name: collect-all-cross-node
io:
  inputs:
    type: object
    properties: {}
  outputs:
    type: object
    properties: {}
phases:
  - first
  - second
---
<phase depends_on="input">first</phase>
<phase depends_on="first" output>second</phase>
""",
        encoding="utf-8",
    )
    for phase in ("first", "second"):
        (tmp_path / "phases" / phase).mkdir(parents=True)
        (tmp_path / "phases" / phase / "SKILL.md").write_text(
            _AGENT_SKILL_FRONTMATTER + "Just prose, no tags.\n", encoding="utf-8"
        )

    with pytest.raises(SkillLoadError) as excinfo:
        SkillLoader().compile_skill(tmp_path, skill_resolver=mock_skill_resolver)

    issues = getattr(getattr(excinfo.value, "compile_result", None), "issues", [])
    located_files = {str(getattr(issue, "source_path", "")) for issue in issues}
    assert any("first" in loc for loc in located_files)
    assert any("second" in loc for loc in located_files)


# --------------------------------------------------------------------------- #
# Stage-level collect-all (compile-rules §2.1 「同阶段尽量聚合」): independent   #
# defects inside the topology stage (multiple islands / unknown deps), and      #
# across the independent pre-barrier segments (topology + node contents), must  #
# surface in ONE compile instead of revealing themselves one fix at a time.     #
# --------------------------------------------------------------------------- #


def _write_three_phase_graph(root: Path, phase_lines: list[str]) -> None:
    """GRAPH.md with 3 phases a/b/c; frontmatter closes on file line 15, so the
    body <phase> tags land on file lines 16/17/18."""
    body = "\n".join(phase_lines)
    (root / "GRAPH.md").write_text(
        f"""---
schema_version: "v0.3.0"
name: stage-collect-all-test
io:
  inputs:
    type: object
    properties: {{}}
  outputs:
    type: object
    properties: {{}}
phases:
  - a
  - b
  - c
---
{body}
""",
        encoding="utf-8",
    )
    for phase in ("a", "b", "c"):
        (root / "phases" / phase).mkdir(parents=True)
        (root / "phases" / phase / "SKILL.md").write_text(
            _AGENT_SKILL_FRONTMATTER + "<role>R</role>\n<goal>G</goal>\n", encoding="utf-8"
        )


def _issues_with_code(exc: SkillLoadError, code: str) -> list[object]:
    issues = getattr(getattr(exc, "compile_result", None), "issues", None) or []
    return [issue for issue in issues if str(getattr(issue, "rule_id", "")) == code]


def test_two_bare_phases_report_two_islands_together(
    tmp_path: Path, mock_skill_resolver: object
) -> None:
    # b (line 17) and c (line 18) both declare no depends_on: ONE compile must
    # flag BOTH islands, not abort at the first bare phase.
    _write_three_phase_graph(
        tmp_path,
        [
            '<phase depends_on="input" output>a</phase>',
            "<phase>b</phase>",
            "<phase>c</phase>",
        ],
    )

    with pytest.raises(SkillLoadError) as excinfo:
        SkillLoader().compile_skill(tmp_path, skill_resolver=mock_skill_resolver)

    islands = _issues_with_code(excinfo.value, "[F-v3-graph-phase-island]")
    axes = {(getattr(issue, "source_path", None), getattr(issue, "line", None)) for issue in islands}
    field_paths = {getattr(issue, "field_path", None) for issue in islands}
    assert len(islands) == 2, f"expected both islands, got: {islands}"
    assert ("GRAPH.md", 17) in axes
    assert ("GRAPH.md", 18) in axes
    assert field_paths == {"b.depends_on", "c.depends_on"}


def test_two_unknown_deps_reported_together(
    tmp_path: Path, mock_skill_resolver: object
) -> None:
    # b -> ghost1 (line 17) and c -> ghost2 (line 18): ONE compile must flag
    # BOTH unknown dependencies, not just unknown_deps[0].
    _write_three_phase_graph(
        tmp_path,
        [
            '<phase depends_on="input" output>a</phase>',
            '<phase depends_on="ghost1">b</phase>',
            '<phase depends_on="ghost2">c</phase>',
        ],
    )

    with pytest.raises(SkillLoadError) as excinfo:
        SkillLoader().compile_skill(tmp_path, skill_resolver=mock_skill_resolver)

    unknown = _issues_with_code(excinfo.value, "[F-v3-graph-depends-unknown]")
    messages = " | ".join(str(getattr(issue, "message", "")) for issue in unknown)
    assert len(unknown) == 2, f"expected both unknown deps, got: {unknown}"
    assert "ghost1" in messages
    assert "ghost2" in messages


def test_topology_defect_does_not_hide_node_defect(
    tmp_path: Path, mock_skill_resolver: object
) -> None:
    # A broken edge (island on c) and a node content defect (a missing <goal>)
    # are independent: ONE compile must surface both, instead of the topology
    # stage masking every node-level diagnostic.
    _write_three_phase_graph(
        tmp_path,
        [
            '<phase depends_on="input">a</phase>',
            '<phase depends_on="a" output>b</phase>',
            "<phase>c</phase>",
        ],
    )
    (tmp_path / "phases" / "a" / "SKILL.md").write_text(
        _AGENT_SKILL_FRONTMATTER + "<role>R</role>\n", encoding="utf-8"
    )

    with pytest.raises(SkillLoadError) as excinfo:
        SkillLoader().compile_skill(tmp_path, skill_resolver=mock_skill_resolver)

    codes = _all_codes(excinfo.value)
    assert "[F-v3-graph-phase-island]" in codes
    assert "[F-v3-agent-goal-missing]" in codes
