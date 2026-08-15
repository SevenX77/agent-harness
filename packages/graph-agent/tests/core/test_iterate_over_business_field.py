"""iterate.over is a bare business-field reference, resolved on the blackboard.

Decision doc: .kiro/specs/decision-2026-08-15-engine-iterate-over-business-field.md

The product contract (copilot knowledge base KB-06-iterate / KB-01) teaches
``over: chapters`` — a bare business field name — and real skills are authored
that way. State-rooted paths (``data.*`` / ``data.inputs.*``) are an engine
internal that no product surface documents; they stop being accepted. An
``over`` with no dataflow source must already die at compile time instead of
crashing predict/run.
"""

from __future__ import annotations

import json
from pathlib import Path
from textwrap import dedent
from typing import Any

import pytest

from graph_agent.core.compiler import compile_skill
from graph_agent.core.graph_assembler import assemble_graph
from graph_agent.core.loader import SkillLoadError


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def _schema_yaml(properties: dict[str, Any], *, required: list[str] | None = None) -> str:
    schema: dict[str, Any] = {"type": "object", "properties": properties}
    if required is not None:
        schema["required"] = required
    return json.dumps(schema, ensure_ascii=False, indent=4).replace("\n", "\n    ")


def _batch_skill(root: Path, *, over: str) -> None:
    graph_inputs = _schema_yaml(
        {"chapters": {"type": "array", "items": {"type": "object"}}},
        required=["chapters"],
    )
    graph_outputs = _schema_yaml({"summaries": {"type": "array"}})
    phase_inputs = _schema_yaml({"chapter": {"type": "object"}})
    phase_outputs = _schema_yaml({"summaries": {"type": "array"}})

    _write(
        root / "GRAPH.md",
        f"""---
schema_version: "v0.3.0"
name: iterate-over-bare-field
io:
  inputs:
    {graph_inputs}
  outputs:
    {graph_outputs}
phases:
  - worker
---
<phase depends_on="input" output>worker</phase>
""",
    )
    _write(
        root / "phases" / "worker" / "LOGIC.md",
        f"""---
actions: [worker]
validator: false
io:
  inputs:
    {phase_inputs}
  outputs:
    {phase_outputs}
iterate:
  mode: batch
  over: {over}
  item_var: chapter
---
<action>worker</action>
""",
    )
    _write(
        root / "phases" / "worker" / "actions" / "worker.py",
        dedent(
            """
            def worker(inputs):
                return {"summaries": [inputs["chapter"]["chapter_number"]]}
            """
        ).lstrip(),
    )


def test_node_batch_iterate_over_bare_business_field_resolves_root_input(
    tmp_path: Path, mock_skill_resolver: object
) -> None:
    """``over: chapters`` (the documented product syntax) resolves the root
    input list on the blackboard and runs every item."""
    _batch_skill(tmp_path, over="chapters")

    compiled = compile_skill(tmp_path, cache=False, skill_resolver=mock_skill_resolver)
    graph = assemble_graph(compiled, skill_resolver=mock_skill_resolver).graph
    result = graph.invoke(
        {
            "data": {"inputs": {"chapters": [{"chapter_number": 1}, {"chapter_number": 2}]}},
            "flow": {},
            "messages": [],
            "run_id": "r1",
        }
    )

    data = result["data"]
    dumped = data.model_dump() if hasattr(data, "model_dump") else dict(data)
    assert dumped["summaries"] == [[1], [2]]


def test_compile_rejects_iterate_over_with_no_dataflow_source(
    tmp_path: Path, mock_skill_resolver: object
) -> None:
    """An ``over`` naming a field with no root-input / upstream source is a
    compile-time defect ([F-v3-iterate-over-not-list] compile phase), not a
    predict/run crash discovered later."""
    _batch_skill(tmp_path, over="chapter_event_timeline")

    with pytest.raises(SkillLoadError) as exc_info:
        compile_skill(tmp_path, cache=False, skill_resolver=mock_skill_resolver)

    issues = list(getattr(exc_info.value.compile_result, "issues", []) or [])
    codes = {str(getattr(issue, "rule_id", getattr(issue, "code", ""))) for issue in issues}
    assert "[F-v3-iterate-over-not-list]" in codes, codes
    assert any("chapter_event_timeline" in str(getattr(issue, "message", "")) for issue in issues)
