"""E2E proof for D7 per-node golden: a simple linear (non-batch) logic skill must
write a REAL per-node ``phase_outputs`` map (node_id -> that node's outputs) into
the on-disk run result, so Studio headless golden compares per node instead of
silently degrading to a single run-level verdict.

Before this guard, only batch/iterate/terminal phases populated ``phase_outputs``
(via graph_assembler._with_phase_outputs); simple linear phases went through
StateMapper.wrap_phase_output which never recorded it, so flat-result skills lost
per-node granularity.
"""

from __future__ import annotations

import json
from pathlib import Path
from textwrap import dedent
from typing import Any

from graph_agent.core.compiler import compile_skill
from graph_agent.core.graph_assembler import assemble_graph
from graph_agent.core.runner import run_skill


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_two_phase_linear_logic_skill(root: Path) -> None:
    _write(
        root / "GRAPH.md",
        """---
schema_version: "v0.3.0"
name: ws-e8-per-node
io:
  inputs:
    type: object
    required: [topic]
    properties:
      topic:
        type: string
  outputs:
    type: object
    required: [report]
    properties:
      report:
        type: string
phases:
  - segment
  - expand
---
<phase depends_on="input">segment</phase>
<phase depends_on="segment" output>expand</phase>
""",
    )
    _write(
        root / "phases" / "segment" / "LOGIC.md",
        """---
io:
  inputs:
    type: object
    properties:
      topic:
        type: string
  outputs:
    type: object
    properties:
      segments:
        type: string
actions: [segment]
validator: false
---
<action>segment</action>
""",
    )
    _write(
        root / "phases" / "segment" / "actions" / "segment.py",
        dedent(
            """
            def segment(inputs):
                return {"segments": inputs["topic"] + "::seg"}
            """
        ).lstrip(),
    )
    _write(
        root / "phases" / "expand" / "LOGIC.md",
        """---
io:
  inputs:
    type: object
    properties:
      segments:
        type: string
  outputs:
    type: object
    properties:
      report:
        type: string
actions: [expand]
validator: false
---
<action>expand</action>
""",
    )
    _write(
        root / "phases" / "expand" / "actions" / "expand.py",
        dedent(
            """
            def expand(inputs):
                return {"report": inputs["segments"] + "::report"}
            """
        ).lstrip(),
    )


def test_simple_linear_skill_writes_real_per_node_phase_outputs(
    tmp_path: Path,
    mock_skill_resolver: object,
) -> None:
    skill_root = tmp_path / "skill"
    workspace_dir = tmp_path / "workspace"
    _write_two_phase_linear_logic_skill(skill_root)

    result = run_skill(
        skill_root,
        workspace_dir=workspace_dir,
        thread_id="ws-e8-per-node",
        skill_resolver=mock_skill_resolver,
        topic="alpha",
    )

    assert result.success is True

    final_state = json.loads(
        (workspace_dir / "runs" / result.run_id / "final_state.json").read_text(encoding="utf-8")
    )
    phase_outputs = final_state.get("phase_outputs")
    # Real per-node map keyed by phase id, each carrying that node's own outputs.
    assert isinstance(phase_outputs, dict)
    assert set(phase_outputs) == {"segment", "expand"}
    assert phase_outputs["segment"]["segments"] == "alpha::seg"
    assert phase_outputs["expand"]["report"] == "alpha::seg::report"


def _write_batch_open_output_schema_skill(root: Path) -> None:
    """A batch (iterate) phase whose output schema has NO `properties` key — the
    'open schema' branch where a phase payload is computed via a raw dict-delta.
    The reserved phase_outputs meta-key must NOT leak into this node's golden entry.
    """
    root.joinpath("GRAPH.md").parent.mkdir(parents=True, exist_ok=True)
    (root / "GRAPH.md").write_text(
        """---
schema_version: "v0.3.0"
name: ws-e8-batch-open
io:
  inputs:
    type: object
    required: [items]
    properties:
      items:
        type: array
        items:
          type: string
  outputs:
    type: object
    properties:
      seen:
        type: array
phases:
  - worker
---
<phase depends_on="input" output>worker</phase>
""",
        encoding="utf-8",
    )
    logic_dir = root / "phases" / "worker"
    logic_dir.mkdir(parents=True, exist_ok=True)
    # Batch node outputs declare the per-item business value; runtime aggregation
    # must not leak reserved metadata into that value.
    (logic_dir / "LOGIC.md").write_text(
        """---
io:
  inputs:
    type: object
    properties:
      items:
        type: array
        items:
          type: string
      item:
        type: string
  outputs:
    type: object
    properties:
      seen:
        type: string
actions: [worker]
validator: false
batch:
  iterator: items
  item_var: item
  concurrency: 2
---
<action>worker</action>
""",
        encoding="utf-8",
    )
    (logic_dir / "actions").mkdir(parents=True, exist_ok=True)
    (logic_dir / "actions" / "worker.py").write_text(
        dedent(
            """
            def worker(inputs):
                return {"seen": inputs["item"]}
            """
        ).lstrip(),
        encoding="utf-8",
    )


def test_batch_open_schema_phase_outputs_has_no_nested_phase_outputs_leak(
    tmp_path: Path,
    mock_skill_resolver: object,
) -> None:
    _write_batch_open_output_schema_skill(tmp_path)
    compiled = compile_skill(tmp_path, cache=False, skill_resolver=mock_skill_resolver)
    graph = assemble_graph(compiled, skill_resolver=mock_skill_resolver).graph

    result: dict[str, Any] = graph.invoke(
        {"data": {"inputs": {"items": ["a", "b", "c"]}}, "flow": {}, "messages": [], "run_id": "r1"}
    )

    business = result["data"].model_dump()
    worker_entry = business["phase_outputs"]["worker"]
    # The aggregated business field is correct...
    assert worker_entry["seen"] == ["a", "b", "c"]
    # ...and the reserved meta-key did NOT leak in as a spurious nested aggregate.
    assert "phase_outputs" not in worker_entry
