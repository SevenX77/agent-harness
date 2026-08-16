"""A compile diagnostic must name the file it is actually about.

`CompileIssue.source_path` is documented as "skill-relative (posix separators)"
(`core/compiler.py:19`), and Studio projects it directly: the Compile drawer
prints it, and `field-compile-errors.ts` derives the badged node from it.

`_payload_source_path` did not compute a relative path at all — it truncated the
absolute path at its LAST `phases/` or `io/` segment, and collapsed any file
named `GRAPH.md` to the bare string `"GRAPH.md"`. On a skill with nested
subgraphs that is not a shortening, it is a wrong answer:

- measured on `story-deconstruction-v3-lab` (2026-08-15): its 41 markdown files
  produce 32 distinct `source_path` strings, of which only 5 name a file that
  exists at the root; 8 different `GRAPH.md` files all render as `"GRAPH.md"`,
  and `phases/review/SKILL.md` names two different real files;
- end to end: breaking `subgraph/story-analysis/GRAPH.md:19` reported
  `source_path='GRAPH.md' line=19` — the editor marker lands on the ROOT graph,
  on a line whose content is fine.

The location axes only mean something relative to a stated root, and the compile
that owns the root is the one entity that can state it. These tests pin that.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from graph_agent.core.compiler import compile_skill
from graph_agent.core.exceptions import GraphAgentError

_ROOT_GRAPH = """---
schema_version: "v0.3.0"
name: source-path-root
description: fixture
io:
  inputs:
    type: object
    required: [topic]
    properties:
      topic: {type: string}
  outputs:
    type: object
    required: [answer]
    properties:
      answer: {type: string}
phases:
  - alpha
  - beta
---

<phase depends_on="input">alpha</phase>
<phase depends_on="alpha" output>beta</phase>
"""

_SUBGRAPH_NODE = """---
path: {relative_path}
io:
  inputs:
    type: object
    required: [{input_field}]
    properties:
      {input_field}: {{type: string}}
  outputs:
    type: object
    required: [{output_field}]
    properties:
      {output_field}: {{type: string}}
---
"""

_CHILD_GRAPH = """---
schema_version: "v0.3.0"
name: {name}
description: fixture child
io:
  inputs:
    type: object
    required: [{input_field}]
    properties:
      {input_field}: {{type: string}}
  outputs:
    type: object
    required: [{output_field}]
    properties:
      {output_field}: {{type: string}}
phases:
  - review
---

<phase depends_on="input" output>review</phase>
"""

_CHILD_PHASE = """---
llm_role: analyst
io:
  inputs:
    type: object
    required: [{input_field}]
    properties:
      {input_field}: {{type: string}}
  outputs:
    type: object
    required: [{output_field}]
    properties:
      {output_field}: {{type: string}}
---

<role>fixture</role>
<goal>turn {{{input_field}}} into {output_field}</goal>
"""


def _child(
    root: Path,
    directory: str,
    *,
    name: str,
    input_field: str,
    output_field: str,
) -> Path:
    child_root = root / "subgraph" / directory
    (child_root / "phases" / "review").mkdir(parents=True)
    (child_root / "GRAPH.md").write_text(
        _CHILD_GRAPH.format(name=name, input_field=input_field, output_field=output_field),
        encoding="utf-8",
    )
    (child_root / "phases" / "review" / "SKILL.md").write_text(
        _CHILD_PHASE.format(input_field=input_field, output_field=output_field),
        encoding="utf-8",
    )
    return child_root


def _skill(tmp_path: Path) -> Path:
    """Root graph with two sibling subgraphs, each owning a phase named 'review'."""
    root = tmp_path / "skill"
    (root / "phases" / "alpha").mkdir(parents=True)
    (root / "phases" / "beta").mkdir(parents=True)
    (root / "GRAPH.md").write_text(_ROOT_GRAPH, encoding="utf-8")

    _child(root, "first", name="first-child", input_field="topic", output_field="draft")
    _child(root, "second", name="second-child", input_field="draft", output_field="answer")

    (root / "phases" / "alpha" / "SUBGRAPH.md").write_text(
        _SUBGRAPH_NODE.format(
            relative_path="subgraph/first",
            input_field="topic",
            output_field="draft",
        ),
        encoding="utf-8",
    )
    (root / "phases" / "beta" / "SUBGRAPH.md").write_text(
        _SUBGRAPH_NODE.format(
            relative_path="subgraph/second",
            input_field="draft",
            output_field="answer",
        ),
        encoding="utf-8",
    )
    return root


def _issues(root: Path) -> list[object]:
    with pytest.raises(GraphAgentError) as excinfo:
        compile_skill(str(root), cache=False)
    compile_result = getattr(excinfo.value, "compile_result", None)
    return list(getattr(compile_result, "issues", []))


def test_a_child_graph_defect_is_not_reported_at_the_root_graph(tmp_path: Path) -> None:
    root = _skill(tmp_path)
    child_graph = root / "subgraph" / "first" / "GRAPH.md"
    child_graph.write_text(
        child_graph.read_text(encoding="utf-8").replace(
            "phases:", "no_such_graph_field: 1\nphases:", 1
        ),
        encoding="utf-8",
    )

    located = [
        (getattr(issue, "rule_id", None), getattr(issue, "source_path", None))
        for issue in _issues(root)
    ]

    assert ("[F-v3-graph-schema-unknown-field]", "subgraph/first/GRAPH.md") in located, (
        "the unknown field is in the child graph; reporting it as bare 'GRAPH.md' "
        f"points the editor marker at the root graph. got: {located}"
    )
    # The root graph legitimately gets its OWN cascade diagnostic here (its
    # declared output is no longer produced once the child is poisoned), so the
    # assertion is about which file each defect names, not about the root being
    # silent.
    assert ("[F-v3-graph-schema-unknown-field]", "GRAPH.md") not in located, located


def test_same_named_phases_in_two_children_stay_distinguishable(tmp_path: Path) -> None:
    root = _skill(tmp_path)
    for directory in ("first", "second"):
        phase = root / "subgraph" / directory / "phases" / "review" / "SKILL.md"
        phase.write_text(
            phase.read_text(encoding="utf-8").replace(
                "<role>fixture</role>", "<no_such_tag>x</no_such_tag>\n<role>fixture</role>", 1
            ),
            encoding="utf-8",
        )

    paths = [getattr(issue, "source_path", None) for issue in _issues(root)]

    assert "subgraph/first/phases/review/SKILL.md" in paths, paths
    assert "subgraph/second/phases/review/SKILL.md" in paths, paths


def test_a_root_phase_defect_keeps_its_plain_relative_path(tmp_path: Path) -> None:
    """The common case must not move: a root phase is still `phases/<id>/<file>`."""
    root = _skill(tmp_path)
    node = root / "phases" / "alpha" / "SUBGRAPH.md"
    node.write_text(
        node.read_text(encoding="utf-8").replace("path:", "no_such_field: 1\npath:", 1),
        encoding="utf-8",
    )

    paths = [getattr(issue, "source_path", None) for issue in _issues(root)]

    assert "phases/alpha/SUBGRAPH.md" in paths, paths
