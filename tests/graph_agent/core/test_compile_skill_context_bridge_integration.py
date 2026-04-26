"""End-to-end: compile_skill on a parent with a typo'd context_bridge surfaces
the validator's F-context-bridge-output-undeclared FATAL."""
from __future__ import annotations

import textwrap
from pathlib import Path

from graph_agent.core.compiler import compile_skill


def test_compile_skill_propagates_context_bridge_fatal(tmp_path: Path) -> None:
    child = tmp_path / "child.md"
    child.write_text(
        textwrap.dedent(
            """\
            ---
            schema_version: "2.0"
            type: graph
            name: child
            description: child for compile_skill integration test
            io:
              inputs:
                - name: alpha
                  source: runtime
              outputs:
                - name: gamma
                  target: artifact
            phases:
              - name: only
                mode: logic
                execute_steps:
                  - some.module.fn
            ---
            """
        ),
        encoding="utf-8",
    )
    parent = tmp_path / "parent.md"
    parent.write_text(
        textwrap.dedent(
            """\
            ---
            schema_version: "2.0"
            type: graph
            name: parent
            description: parent for compile_skill integration test
            io:
              inputs: []
              outputs: []
            phases:
              - name: delegate_phase
                mode: delegate
                subgraph: child.md
                context_bridge:
                  inputs:
                    parent_a: alpha
                  outputs:
                    gammma: parent_g
            ---
            """
        ),
        encoding="utf-8",
    )

    result = compile_skill(parent)

    rule_ids = sorted(i.rule_id for i in result.fatals)
    assert "F-context-bridge-output-undeclared" in rule_ids
    assert result.passed is False
