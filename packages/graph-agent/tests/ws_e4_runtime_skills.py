"""Skill fixtures for WS-E4 runtime edge event tests."""

from __future__ import annotations

import json
from pathlib import Path
from textwrap import dedent
from typing import Any


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _schema_yaml(properties: dict[str, Any], *, required: list[str] | None = None) -> str:
    schema: dict[str, Any] = {"type": "object", "properties": properties}
    if required is not None:
        schema["required"] = required
    return json.dumps(schema, ensure_ascii=False, indent=4).replace("\n", "\n    ")


def _write_graph(
    root: Path,
    *,
    name: str,
    inputs: dict[str, Any],
    outputs: dict[str, Any],
    phases: list[str],
    phase_edges: str,
    required_inputs: list[str] | None = None,
) -> None:
    phase_list = "\n".join(f"  - {phase}" for phase in phases)
    _write(
        root / "GRAPH.md",
        f"""---
schema_version: "v0.3.0"
name: {name}
io:
  inputs:
    {_schema_yaml(inputs, required=required_inputs)}
  outputs:
    {_schema_yaml(outputs)}
phases:
{phase_list}
---
{phase_edges}
""",
    )


def write_logic_phase(
    root: Path,
    phase_id: str,
    *,
    inputs: dict[str, Any],
    outputs: dict[str, Any],
    action_body: str,
    required: list[str] | None = None,
    iterate: str | None = None,
) -> None:
    iterate_block = f"{iterate.rstrip()}\n" if iterate else ""
    _write(
        root / "phases" / phase_id / "LOGIC.md",
        f"""---
io:
  inputs:
    {_schema_yaml(inputs, required=required)}
  outputs:
    {_schema_yaml(outputs)}
actions: [{phase_id}]
validator: false
{iterate_block}---
<action>{phase_id}</action>
""",
    )
    _write(
        root / "phases" / phase_id / "actions" / f"{phase_id}.py",
        dedent(action_body).lstrip(),
    )


def write_serial_two_phase_skill(root: Path, *, name: str = "ws-e4-runtime-serial") -> None:
    _write_graph(
        root,
        name=name,
        inputs={"source": {"type": "string"}},
        outputs={"answer": {"type": "string"}},
        phases=["prepare", "finish"],
        phase_edges='<phase depends_on="input">prepare</phase>\n'
        '<phase depends_on="prepare" output>finish</phase>',
        required_inputs=["source"],
    )
    write_logic_phase(
        root,
        "prepare",
        inputs={"source": {"type": "string"}},
        outputs={"prepared": {"type": "string"}},
        required=["source"],
        action_body="""
            def prepare(context):
                return {"prepared": f"{context['source']}:prepared"}
        """,
    )
    write_logic_phase(
        root,
        "finish",
        inputs={"prepared": {"type": "string"}},
        outputs={"answer": {"type": "string"}},
        required=["prepared"],
        action_body="""
            def finish(context):
                return {"answer": f"{context['prepared']}:done"}
        """,
    )


def write_loop_accumulate_skill(root: Path) -> None:
    _write_graph(
        root,
        name="ws-e4-runtime-loop-reduce",
        inputs={"items": {"type": "array"}},
        outputs={"collected": {"type": "array"}},
        phases=["collect"],
        phase_edges='<phase depends_on="input" output>collect</phase>',
    )
    write_logic_phase(
        root,
        "collect",
        inputs={"item": {}, "collected": {}},
        outputs={"piece": {}},
        required=["item", "collected"],
        iterate="""
iterate:
  mode: loop
  over: data.inputs.items
  item_var: item
  accumulate:
    var: collected
    init: []
    from: piece
    merge: append
""",
        action_body="""
            def collect(context):
                return {"piece": context["item"]}
        """,
    )


def write_batch_iterate_skill(root: Path) -> None:
    _write_graph(
        root,
        name="ws-e4-runtime-batch-dispatch",
        inputs={"items": {"type": "array"}},
        outputs={"seen": {"type": "array"}},
        phases=["worker"],
        phase_edges='<phase depends_on="input" output>worker</phase>',
    )
    write_logic_phase(
        root,
        "worker",
        inputs={"item": {}},
        outputs={"seen": {}},
        required=["item"],
        iterate="""
iterate:
  mode: batch
  over: data.inputs.items
  item_var: item
  concurrency: 2
""",
        action_body="""
            def worker(context):
                return {"seen": context["item"]}
        """,
    )


def write_file_input_skill(root: Path) -> None:
    _write_graph(
        root,
        name="ws-e4-runtime-file-input",
        inputs={"title": {"type": "string"}},
        outputs={"answer": {"type": "string"}},
        phases=["reader"],
        phase_edges='<phase depends_on="input" output>reader</phase>',
        required_inputs=["title"],
    )
    write_logic_phase(
        root,
        "reader",
        inputs={
            "title": {"type": "string"},
            "body": {
                "type": "string",
                "source": "file",
                "path": "inputs/body.md",
            },
        },
        outputs={"answer": {"type": "string"}},
        required=["title", "body"],
        action_body="""
            def reader(context):
                return {"answer": f"{context['title']}::{context['body']}"}
        """,
    )
