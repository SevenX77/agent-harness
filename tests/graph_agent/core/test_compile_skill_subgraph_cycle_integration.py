"""End-to-end: compile_skill on a self-cycling parent surfaces F-subgraph-cycle."""
from __future__ import annotations

from pathlib import Path

from graph_agent.core.compiler import compile_skill


def test_compile_skill_propagates_subgraph_cycle(tmp_path: Path) -> None:
    parent = tmp_path / "parent.md"
    parent.write_text(
        "---\n"
        'schema_version: "2.0"\n'
        "type: graph\n"
        "name: parent\n"
        "description: parent for cycle integration test\n"
        "io:\n  inputs: []\n  outputs: []\n"
        "phases:\n"
        "  - name: self_loop\n"
        "    mode: delegate\n"
        "    subgraph: parent.md\n"
        "    context_bridge:\n"
        "      inputs: {}\n"
        "      outputs: {}\n"
        "---\n",
        encoding="utf-8",
    )

    result = compile_skill(parent)

    rule_ids = sorted(i.rule_id for i in result.fatals)
    assert "F-subgraph-cycle" in rule_ids
    assert result.passed is False
