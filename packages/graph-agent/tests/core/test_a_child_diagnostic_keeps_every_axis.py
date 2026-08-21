"""A defect found inside a child skill reaches the parent with every axis intact.

A subgraph phase compiles its child skill, and when that child fails, the parent
catches the error and re-raises the child's diagnostics as its own. That seam
rebuilt each diagnostic field by field, so an axis nobody remembered to list
there simply did not exist any more once the parent reported it.

`conflicting_phase` is the one that proved it. It was added so the sequential-
overwrite rule could name the OTHER phase structurally instead of only inside
its English sentence (ledger K3), and it worked — at the top level. One subgraph
deep the field arrived `None`, and the canvas was back to reading the sentence.

`source_path` is the axis that must be REBUILT rather than carried: it is
relative to whichever root stated it, so the child's own relative path has to be
re-rooted before the parent renders it against its own root. That distinction —
one axis re-derived, all others carried — is what these tests pin.
"""

from __future__ import annotations

import json
from dataclasses import fields
from pathlib import Path

import pytest

from graph_agent.core.compiler import CompileIssue, compile_skill
from graph_agent.core.exceptions import GraphAgentError


def _schema(properties: dict[str, object], required: list[str] | None = None) -> str:
    body: dict[str, object] = {"type": "object", "properties": properties}
    if required is not None:
        body["required"] = required
    return json.dumps(body, ensure_ascii=False, indent=4).replace("\n", "\n    ")


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def _logic_phase(root: Path, name: str) -> None:
    _write(
        root / "phases" / name / "LOGIC.md",
        f"""---
io:
  inputs:
    {_schema({"topic": {"type": "string"}}, required=["topic"])}
  outputs:
    {_schema({"summary": {"type": "string"}})}
actions: [{name}]
validator: false
---
<action>{name}</action>
""",
    )
    _write(
        root / "phases" / name / "actions" / f"{name}.py",
        f'def {name}(inputs):\n    return {{"summary": "x"}}\n',
    )


def _conflict_skill(root: Path, name: str) -> None:
    """Two chained phases declaring the same output: the sequential-overwrite rule."""
    _write(
        root / "GRAPH.md",
        f"""---
schema_version: "v0.3.0"
name: {name}
io:
  inputs:
    {_schema({"topic": {"type": "string"}}, required=["topic"])}
  outputs:
    {_schema({"summary": {"type": "string"}})}
phases:
  - draft
  - revise
---
<phase depends_on="input">draft</phase>
<phase depends_on="draft" output>revise</phase>
""",
    )
    _logic_phase(root, "draft")
    _logic_phase(root, "revise")


def _wrapper_skill(root: Path, name: str, child_dir: str, phase_name: str) -> None:
    """A skill whose single phase is a subgraph pointing at `subgraph/<child_dir>`."""
    _write(
        root / "GRAPH.md",
        f"""---
schema_version: "v0.3.0"
name: {name}
io:
  inputs:
    {_schema({"topic": {"type": "string"}}, required=["topic"])}
  outputs:
    {_schema({"summary": {"type": "string"}})}
phases:
  - {phase_name}
---
<phase depends_on="input" output>{phase_name}</phase>
""",
    )
    _write(
        root / "phases" / phase_name / "SUBGRAPH.md",
        f"""---
name: {phase_name}
path: subgraph/{child_dir}
io:
  inputs:
    {_schema({"topic": {"type": "string"}}, required=["topic"])}
  outputs:
    {_schema({"summary": {"type": "string"}})}
---
<subgraph>{phase_name}</subgraph>
""",
    )


@pytest.fixture
def nested_conflict_root(tmp_path: Path) -> Path:
    """parent → subgraph/mid → subgraph/leaf, the conflict in the deepest child."""
    _wrapper_skill(tmp_path, "k6_parent", "mid", "mid_stage")
    _wrapper_skill(tmp_path / "subgraph" / "mid", "k6_mid", "leaf", "leaf_stage")
    _conflict_skill(tmp_path / "subgraph" / "mid" / "subgraph" / "leaf", "k6_leaf")
    return tmp_path


def _issues(root: Path) -> list[CompileIssue]:
    with pytest.raises(GraphAgentError) as caught:
        compile_skill(str(root))
    result = getattr(caught.value, "compile_result", None)
    assert result is not None, "a compile failure must carry its aggregated issues"
    return list(result.issues)


def _overwrite_issue(root: Path) -> CompileIssue:
    matches = [
        issue
        for issue in _issues(root)
        if issue.rule_id == "[F-v3-sequential-overwrite-unauthorized]"
    ]
    assert len(matches) == 1, f"expected exactly one overwrite issue, got {matches}"
    return matches[0]


def test_a_two_level_child_conflict_still_names_the_upstream_phase(nested_conflict_root: Path) -> None:
    issue = _overwrite_issue(nested_conflict_root)

    assert issue.conflicting_phase == "draft"


def test_the_same_issue_keeps_its_field_and_message(nested_conflict_root: Path) -> None:
    issue = _overwrite_issue(nested_conflict_root)

    assert issue.field_path == "io.outputs.properties.summary"
    assert "'revise' sequentially overwrites field 'summary'" in issue.message


def test_the_rebuilt_axis_is_the_one_that_names_the_root(nested_conflict_root: Path) -> None:
    # source_path is the exception: it only means something against a stated
    # root, so the child's own relative answer is re-rooted and re-rendered
    # against the parent's.
    issue = _overwrite_issue(nested_conflict_root)

    assert issue.source_path == "subgraph/mid/subgraph/leaf/phases/revise/LOGIC.md"


def test_every_issue_axis_is_accounted_for_at_the_child_seam() -> None:
    """Adding an axis to CompileIssue must be a decision at this seam, not an omission.

    The seam used to list the fields it copied, which is a shape where the next
    field added travels fine everywhere except across a subgraph boundary — and
    nothing fails, so nobody finds out. This test is the reminder: name the new
    field in one of the two sets below and say which one it is.
    """
    carried = {"rule_id", "line", "field_path", "message", "conflicting_phase"}
    rebuilt = {"source_path"}
    # `severity` is not carried and not rebuilt: the loader raises FATALs only,
    # and states that once in `_compile_result` rather than per diagnostic.
    stated_elsewhere = {"severity"}

    assert {field.name for field in fields(CompileIssue)} == carried | rebuilt | stated_elsewhere
