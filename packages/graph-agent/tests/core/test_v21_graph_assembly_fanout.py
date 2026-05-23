from __future__ import annotations

from pathlib import Path
from shutil import copytree

import pytest
from graph_agent.core.compiler import compile_skill
from graph_agent.core.exceptions import GraphAgentFatalError
from graph_agent.core.graph_assembler import assemble_graph

FIXTURE = Path(__file__).parents[1] / "fixtures" / "fake_canvas_fanout"


def test_canvas_fanout_fixture_merges_disjoint_outputs() -> None:
    graph = assemble_graph(compile_skill(FIXTURE, cache=False)).graph

    result = graph.invoke({"data": {}, "flow": {}, "messages": [], "run_id": "fanout"})

    assert result["data"] == {"a_out": 1, "b_out": 2}


def test_canvas_fanout_fixture_conflicting_key_is_fatal(tmp_path: Path) -> None:
    root = tmp_path / "fake_canvas_fanout"
    copytree(FIXTURE, root)
    (root / "phases" / "branch_b" / "actions" / "write_b.py").write_text(
        "def write_b(context):\n    return {'a_out': 2}\n", encoding="utf-8"
    )
    graph = assemble_graph(compile_skill(root, cache=False)).graph

    with pytest.raises(GraphAgentFatalError, match=r"\[F-v3-state-conflict\].*key='a_out'"):
        graph.invoke({"data": {}, "flow": {}, "messages": [], "run_id": "fanout-conflict"})
