"""RED tests for WS-E1 Step5 subgraph IO relaxation."""

from __future__ import annotations

import json
from pathlib import Path
from textwrap import dedent
from typing import Any

import pytest

from graph_agent.core.compiler import compile_skill
from graph_agent.core.graph_assembler import assemble_graph


class DictSkillResolver:
    def __init__(self, roots: dict[str, Path]) -> None:
        self.roots = roots

    def resolve_skill(self, skill_id: str) -> Path:
        return self.roots[skill_id]


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _schema_yaml(properties: dict[str, Any], *, required: list[str] | None = None) -> str:
    schema: dict[str, Any] = {"type": "object", "properties": properties}
    if required is not None:
        schema["required"] = required
    return json.dumps(schema, ensure_ascii=False, indent=4).replace("\n", "\n    ")


def _business_data(result: dict[str, Any]) -> dict[str, Any]:
    data = result["data"]
    if hasattr(data, "model_dump"):
        return data.model_dump()
    return dict(data)


def _write_graph(
    root: Path,
    *,
    name: str,
    input_properties: dict[str, Any],
    output_properties: dict[str, Any],
    phase: str,
    input_required: list[str] | None = None,
    output_required: list[str] | None = None,
) -> None:
    input_yaml = _schema_yaml(input_properties, required=input_required)
    output_yaml = _schema_yaml(output_properties, required=output_required)
    _write(
        root / "GRAPH.md",
        f"""---
schema_version: "v0.3.0"
name: {name}
io:
  inputs:
    {input_yaml}
  outputs:
    {output_yaml}
phases:
  - {phase}
---
<phase depends_on="input" output>{phase}</phase>
""",
    )


def _write_subgraph_phase(
    root: Path,
    *,
    child_path: Path,
    input_properties: dict[str, Any],
    output_properties: dict[str, Any],
    input_required: list[str] | None = None,
    output_required: list[str] | None = None,
) -> None:
    input_yaml = _schema_yaml(input_properties, required=input_required)
    output_yaml = _schema_yaml(output_properties, required=output_required)
    _write(
        root / "phases" / "delegate" / "SUBGRAPH.md",
        f"""---
path: {child_path}
io:
  inputs:
    {input_yaml}
  outputs:
    {output_yaml}
validator: false
---
""",
    )


def _write_logic_phase(
    root: Path,
    *,
    input_properties: dict[str, Any],
    output_properties: dict[str, Any],
    action_body: str,
    input_required: list[str] | None = None,
    output_required: list[str] | None = None,
) -> None:
    input_yaml = _schema_yaml(input_properties, required=input_required)
    output_yaml = _schema_yaml(output_properties, required=output_required)
    _write(
        root / "phases" / "worker" / "LOGIC.md",
        f"""---
io:
  inputs:
    {input_yaml}
  outputs:
    {output_yaml}
actions: [worker]
validator: false
---
<action>worker</action>
""",
    )
    _write(root / "phases" / "worker" / "actions" / "worker.py", dedent(action_body).lstrip())


def _subgraph_skill(
    root: Path,
    *,
    parent_inputs: dict[str, Any],
    child_inputs: dict[str, Any],
    parent_outputs: dict[str, Any],
    child_outputs: dict[str, Any] | None = None,
    action_body: str | None = None,
) -> tuple[Path, Path, DictSkillResolver]:
    parent = root / "parent"
    child = parent / "subgraphs" / "child"
    child_outputs = child_outputs or parent_outputs

    _write_graph(
        parent,
        name="ws-e1-step5-parent",
        input_properties=parent_inputs,
        output_properties=parent_outputs,
        phase="delegate",
        input_required=list(parent_inputs),
        output_required=list(parent_outputs),
    )
    _write_subgraph_phase(
        parent,
        child_path=child,
        input_properties=parent_inputs,
        output_properties=parent_outputs,
        input_required=list(parent_inputs),
        output_required=list(parent_outputs),
    )
    _write_graph(
        child,
        name="ws-e1-step5-child",
        input_properties=child_inputs,
        output_properties=child_outputs,
        phase="worker",
        input_required=list(child_inputs),
        output_required=list(child_outputs),
    )
    _write_logic_phase(
        child,
        input_properties=child_inputs,
        output_properties=child_outputs,
        input_required=list(child_inputs),
        output_required=list(child_outputs),
        action_body=action_body
        or """
            def worker(inputs):
                return {"report": inputs.get("child_text", inputs.get("shared_text", "missing"))}
        """,
    )
    return parent, child, DictSkillResolver({"child": child})


@pytest.mark.parametrize(
    ("case_name", "parent_inputs", "child_inputs"),
    [
        (
            "parent_input_superset",
            {"shared_text": {"type": "string"}, "parent_extra": {"type": "string"}},
            {"shared_text": {"type": "string"}},
        ),
        (
            "different_input_sets",
            {"parent_alias": {"type": "string"}},
            {"child_text": {"type": "string"}},
        ),
    ],
)
def test_subgraph_input_mismatch_compiles_without_mirror_contract(
    tmp_path: Path,
    case_name: str,
    parent_inputs: dict[str, Any],
    child_inputs: dict[str, Any],
) -> None:
    del case_name
    parent, _, resolver = _subgraph_skill(
        tmp_path,
        parent_inputs=parent_inputs,
        child_inputs=child_inputs,
        parent_outputs={"report": {"type": "string"}},
    )

    compiled = compile_skill(parent, cache=False, skill_resolver=resolver)

    assert compiled.nodes[0].phase_name == "delegate"


def test_subgraph_runtime_slices_parent_blackboard_with_relaxed_inputs(tmp_path: Path) -> None:
    outputs = {
        "report": {"type": "string"},
        "seen_keys": {"type": "array", "items": {"type": "string"}},
    }
    parent, _, resolver = _subgraph_skill(
        tmp_path,
        parent_inputs={"shared_text": {"type": "string"}, "parent_extra": {"type": "string"}},
        child_inputs={"shared_text": {"type": "string"}},
        parent_outputs=outputs,
        action_body="""
            def worker(inputs):
                return {
                    "report": inputs["shared_text"].upper(),
                    "seen_keys": sorted(inputs.keys()),
                }
        """,
    )

    compiled = compile_skill(parent, cache=False, skill_resolver=resolver)
    graph = assemble_graph(compiled, skill_resolver=resolver).graph
    result = graph.invoke(
        {
            "data": {
                "inputs": {
                    "shared_text": "child input",
                    "parent_extra": "allowed into parent subgraph slice",
                    "parent_secret": "must not leak",
                }
            },
            "flow": {},
            "messages": [],
            "run_id": "r1",
        }
    )

    data = _business_data(result)
    assert data["report"] == "CHILD INPUT"
    assert data["seen_keys"] == ["shared_text"]
    assert result["data"]["phase_outputs"]["delegate"]["report"] == "CHILD INPUT"
    assert result["data"]["phase_outputs"]["delegate"]["seen_keys"] == ["shared_text"]


def test_subgraph_output_mismatch_now_compiles_without_1to1_gate(tmp_path: Path) -> None:
    # WS-E1 Step5 / skill-syntax §2.4: the parent/child io.outputs 1:1 equality
    # gate is relaxed. A subgraph whose declared outputs differ from the child's
    # now COMPILES instead of raising [F-v3-subgraph-io-mismatch] — StateMapper
    # merges by the parent's declared outputs at runtime, so field sets need not
    # match 1:1.
    parent, _, resolver = _subgraph_skill(
        tmp_path,
        parent_inputs={"shared_text": {"type": "string"}},
        child_inputs={"shared_text": {"type": "string"}},
        parent_outputs={"parent_report": {"type": "string"}},
        child_outputs={"child_report": {"type": "string"}},
        action_body="""
            def worker(inputs):
                return {"child_report": inputs["shared_text"]}
        """,
    )

    compiled = compile_skill(parent, cache=False, skill_resolver=resolver)

    assert compiled.nodes[0].phase_name == "delegate"
