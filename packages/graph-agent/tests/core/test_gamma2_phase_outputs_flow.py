from __future__ import annotations

import json
from pathlib import Path

from graph_agent.core.compiler import compile_skill
from graph_agent.core.graph_assembler import assemble_graph


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _base(root: Path, phases: str) -> None:
    _write(
        root / "GRAPH.md",
        """---
schema_version: "2.1"
name: gamma2-flow
---
<input src="io/inputs.json" />
<output src="io/outputs.json" />
"""
        + phases,
    )
    _write(root / "io" / "inputs.json", "{}\n")
    _write(root / "io" / "outputs.json", json.dumps({}, ensure_ascii=False))


def _logic_action(root: Path, phase: str, action: str, body: str) -> None:
    _write(
        root / "phases" / phase / "LOGIC.md",
        f"""---
mode: logic
---
<python_callable>
{action}
</python_callable>
""",
    )
    _write(root / "phases" / phase / "actions" / f"{action}.py", body)


def test_downstream_phase_reads_upstream_phase_outputs_in_same_graph(tmp_path: Path) -> None:
    _base(
        tmp_path,
        '<phase id="segment" src="phases/segment" depends_on="" />\n'
        '<phase id="review" src="phases/review" depends_on="segment" />\n',
    )
    _logic_action(
        tmp_path,
        "segment",
        "segment",
        "def segment(context):\n    context.set('segments_summary', 'chapter summary')\n",
    )
    _logic_action(
        tmp_path,
        "review",
        "review",
        "def review(context):\n"
        "    return {'review_input': context.get('segments_summary', 'missing')}\n",
    )

    result = assemble_graph(compile_skill(tmp_path, cache=False)).graph.invoke(
        {"data": {"inputs": {}}, "flow": {}, "messages": [], "run_id": "r1"}
    )

    assert result["data"]["phase_outputs"]["review"] == {"review_input": "chapter summary"}
