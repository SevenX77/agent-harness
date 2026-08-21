"""A two-phase conflict has to name both phases in fields, not only in prose.

``_validate_sequential_overwrites`` knows exactly which field collides and
which upstream phase wrote it first — both are local variables at the moment it
raises. Only the English sentence carried them out: ``field_path`` was filled
with ``allow_sequential_overwrite``, the frontmatter key that FIXES the
conflict, and the upstream phase had no slot at all.

So the one consumer that reads the structured axes reads the wrong thing. The
canvas popover takes ``CompileError.field`` as the overwritten field name and
would render "Field ``allow_sequential_overwrite`` is also output by upstream
node …" — and the allow-list check it drives (`currentFileAllowsSequentialOverwrite`)
asks whether ``allow_sequential_overwrite`` lists itself, which is never true,
so the warning could never clear. Everything else about the conflict reached
the UI by regexing the sentence (ledger K3).

``_validate_parallel_writes`` — same file, same "one field, two writers"
family — already points ``field_path`` at ``io.outputs.properties.<key>``. This
aligns its sibling rule to that convention and gives the second participant a
field of its own.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from graph_agent.core.compiler import compile_skill
from graph_agent.core.exceptions import GraphAgentError

_FIELD = "summary"
_UPSTREAM = "draft"
_DOWNSTREAM = "revise"


def _schema(properties: dict[str, Any], *, required: list[str] | None = None) -> str:
    schema: dict[str, Any] = {"type": "object", "properties": properties}
    if required is not None:
        schema["required"] = required
    return json.dumps(schema, ensure_ascii=False, indent=4).replace("\n", "\n    ")


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def _logic_phase(root: Path, name: str, *, inputs: dict[str, Any], required: list[str]) -> None:
    _write(
        root / "phases" / name / "LOGIC.md",
        f"""---
io:
  inputs:
    {_schema(inputs, required=required)}
  outputs:
    {_schema({_FIELD: {"type": "string"}})}
actions: [{name}]
validator: false
---
<action>{name}</action>
""",
    )
    _write(
        root / "phases" / name / "actions" / f"{name}.py",
        f'def {name}(inputs):\n    return {{"{_FIELD}": "text"}}\n',
    )


def _overwriting_skill(root: Path) -> Path:
    """Two chained phases that both declare the same output field."""
    _write(
        root / "GRAPH.md",
        f"""---
schema_version: "v0.3.0"
name: conflict-names-both-phases
io:
  inputs:
    {_schema({"topic": {"type": "string"}}, required=["topic"])}
  outputs:
    {_schema({_FIELD: {"type": "string"}})}
phases:
  - {_UPSTREAM}
  - {_DOWNSTREAM}
---
<phase depends_on="input">{_UPSTREAM}</phase>
<phase depends_on="{_UPSTREAM}" output>{_DOWNSTREAM}</phase>
""",
    )
    _logic_phase(root, _UPSTREAM, inputs={"topic": {"type": "string"}}, required=["topic"])
    _logic_phase(root, _DOWNSTREAM, inputs={_FIELD: {"type": "string"}}, required=[_FIELD])
    return root


def _sequential_overwrite_issue(tmp_path: Path) -> Any:
    skill = _overwriting_skill(tmp_path / "skill")
    with pytest.raises(GraphAgentError) as caught:
        compile_skill(skill, cache=False)

    compile_result = getattr(caught.value, "compile_result", None)
    assert compile_result is not None, "the aggregated diagnostics must ride on the exception seam"
    matching = [
        issue
        for issue in compile_result.issues
        if issue.rule_id == "[F-v3-sequential-overwrite-unauthorized]"
    ]
    assert len(matching) == 1, f"expected exactly one overwrite diagnostic, got {compile_result.issues}"
    return matching[0]


def test_the_diagnostic_points_at_the_overwritten_field(tmp_path: Path) -> None:
    issue = _sequential_overwrite_issue(tmp_path)

    assert issue.field_path == f"io.outputs.properties.{_FIELD}", (
        "field_path must locate the field the conflict is ABOUT, the way "
        "[F-v3-parallel-write-conflict] does — not the frontmatter key that resolves it"
    )


def test_the_diagnostic_names_the_upstream_phase_it_conflicts_with(tmp_path: Path) -> None:
    issue = _sequential_overwrite_issue(tmp_path)

    assert issue.conflicting_phase == _UPSTREAM, (
        "the phase that wrote the field first is a fact the validator already had; "
        "a consumer must not have to parse it back out of the message"
    )


def test_a_single_writer_leaves_the_conflict_axis_empty(tmp_path: Path) -> None:
    """Most rules are about one phase, and they must not claim a second one."""
    skill = _overwriting_skill(tmp_path / "skill")
    logic = skill / "phases" / _DOWNSTREAM / "LOGIC.md"
    logic.write_text(
        logic.read_text(encoding="utf-8").replace(
            "validator: false",
            f"validator: false\nallow_sequential_overwrite: [{_FIELD}]",
        ),
        encoding="utf-8",
        newline="\n",
    )

    compiled = compile_skill(skill, cache=False)

    assert compiled is not None, "declaring the overwrite makes the skill compile"
