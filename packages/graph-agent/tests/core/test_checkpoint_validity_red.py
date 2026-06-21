"""RED tests for node-scoped checkpoint validity."""

from __future__ import annotations

import json
from pathlib import Path
from textwrap import dedent
from typing import Any

from graph_agent.core.compiler import compile_skill


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _schema(properties: dict[str, Any], *, required: list[str] | None = None) -> str:
    payload: dict[str, Any] = {"type": "object", "properties": properties}
    if required is not None:
        payload["required"] = required
    return json.dumps(payload, ensure_ascii=False, indent=4).replace("\n", "\n    ")


def _fanout_skill(root: Path) -> None:
    graph_input = _schema({"topic": {"type": "string"}}, required=["topic"])
    graph_output = _schema(
        {
            "a": {"type": "string"},
            "b": {"type": "string"},
            "summary": {"type": "string"},
        },
        required=["a", "b", "summary"],
    )
    _write(
        root / "GRAPH.md",
        f"""---
schema_version: "v0.3.0"
name: checkpoint-validity-red
io:
  inputs:
    {graph_input}
  outputs:
    {graph_output}
phases:
  - prepare
  - branch_a
  - branch_b
  - assemble
---
<phase depends_on="input">prepare</phase>
<phase depends_on="prepare">branch_a</phase>
<phase depends_on="prepare">branch_b</phase>
<phase depends_on="branch_a,branch_b" output>assemble</phase>
""",
    )
    _logic_phase(
        root,
        "prepare",
        inputs=graph_input,
        outputs=_schema({"prepared": {"type": "string"}}, required=["prepared"]),
        action_body='return {"prepared": f"prepared:{context[\'topic\']}"}',
    )
    _logic_phase(
        root,
        "branch_a",
        inputs=_schema({"prepared": {"type": "string"}}, required=["prepared"]),
        outputs=_schema({"a": {"type": "string"}}, required=["a"]),
        action_body='return {"a": f"a:{context[\'prepared\']}"}',
    )
    _logic_phase(
        root,
        "branch_b",
        inputs=_schema({"prepared": {"type": "string"}}, required=["prepared"]),
        outputs=_schema({"b": {"type": "string"}}, required=["b"]),
        action_body='return {"b": f"b:{context[\'prepared\']}"}',
    )
    _logic_phase(
        root,
        "assemble",
        inputs=_schema(
            {"a": {"type": "string"}, "b": {"type": "string"}},
            required=["a", "b"],
        ),
        outputs=_schema({"summary": {"type": "string"}}, required=["summary"]),
        action_body='return {"summary": f"{context[\'a\']}|{context[\'b\']}"}',
    )


def _logic_phase(
    root: Path,
    phase_id: str,
    *,
    inputs: str,
    outputs: str,
    action_body: str,
) -> None:
    _write(
        root / "phases" / phase_id / "LOGIC.md",
        f"""---
io:
  inputs:
    {inputs}
  outputs:
    {outputs}
actions: [{phase_id}]
validator: false
---
<action>{phase_id}</action>
""",
    )
    _write(
        root / "phases" / phase_id / "actions" / f"{phase_id}.py",
        dedent(
            f"""
            def {phase_id}(context):
                {action_body}
            """
        ).lstrip(),
    )


def test_checkpoint_validity_is_node_scoped_not_global(
    tmp_path: Path,
    mock_skill_resolver: object,
) -> None:
    from graph_agent.core.checkpoint_validity import checkpoint_validity_by_phase

    skill_root = tmp_path / "skill"
    _fanout_skill(skill_root)
    compiled = compile_skill(skill_root, skill_resolver=mock_skill_resolver)

    validity = checkpoint_validity_by_phase(compiled, dirty_phase_ids={"branch_b"})

    assert validity == {
        "prepare": True,
        "branch_a": True,
        "branch_b": False,
        "assemble": False,
    }
