"""An output's `target` is an enum, and compile has to say so.

A session probing the declaration contract wrote `target: __probe_invalid__`
into GRAPH.md and compiled: `status: ok`, zero defects, and the junk value
carried straight into the manifest and io_schema (exp-b-round3, 2026-08-03).
At run time the writer only fires for `file` or `artifact`, so the run produced
no file and said nothing about why — the failure mode a user sees as
"artifacts/ is always empty".

Compile is the single exit for that kind of defect, so it belongs here rather
than in a Studio-side check; and with it in place the compiler can serve as the
contract oracle a session naturally reaches for.

It reports under the existing `[F-v3-graph-io-schema-invalid]` family rather than
a new code: the registry is frozen at 97 codes by design (R4.3 / design §6.5), and
an unknown `target` IS an invalid inline io schema — the specific value and the
legal set travel in the message and `field_path`, which is what a reader needs.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from graph_agent.core.compiler import compile_skill
from graph_agent.core.exceptions import GraphCompileError

GRAPH_TEMPLATE = """---
schema_version: "v0.3.0"
name: target-demo
description: target declaration probe
io:
  inputs:
    type: object
    properties:
      topic:
        type: string
  outputs:
    type: object
    required: [answer]
    properties:
      answer:
        type: object
{target_line}
        properties:
          text:
            type: string
phases:
  - draft
---
<phase depends_on="input" output>draft</phase>
"""

LOGIC = """---
io:
  inputs:
    type: object
    properties:
      topic:
        type: string
  outputs:
    type: object
    properties:
      answer:
        type: object
actions: [draft]
validator: false
---
<action>draft</action>
"""

ACTION = '''
def run(inputs):
    return {"answer": {"text": "ok"}}
'''


def _write_action(phase_dir):
    actions = phase_dir / "actions"
    actions.mkdir(parents=True, exist_ok=True)
    (actions / "draft.py").write_text(ACTION, encoding="utf-8")


def _skill(root: Path, target_line: str) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "GRAPH.md").write_text(
        GRAPH_TEMPLATE.format(target_line=target_line), encoding="utf-8"
    )
    phase_dir = root / "phases" / "draft"
    phase_dir.mkdir(parents=True)
    (phase_dir / "LOGIC.md").write_text(LOGIC, encoding="utf-8")
    _write_action(phase_dir)
    return root


def _compile_issues(root: Path) -> list[str]:
    try:
        compile_skill(root, cache=False)
    except GraphCompileError as exc:
        issues = getattr(getattr(exc, "compile_result", None), "issues", []) or []
        return [f"{getattr(issue, 'rule_id', '')} {getattr(issue, 'message', '')}" for issue in issues]
    return []


def test_an_unknown_target_is_a_compile_defect(tmp_path: Path) -> None:
    root = _skill(tmp_path / "unknown", '        target: __probe_invalid__')

    issues = _compile_issues(root)

    assert any("[F-v3-graph-io-schema-invalid]" in issue for issue in issues), issues
    assert any("file" in issue and "artifact" in issue for issue in issues), (
        "诊断必须给出合法取值,否则 agent 还是只能猜"
    )


@pytest.mark.parametrize("target", ["file", "artifact"])
def test_the_two_written_targets_compile_clean(tmp_path: Path, target: str) -> None:
    root = _skill(tmp_path / target, f"        target: {target}")

    assert _compile_issues(root) == []


def test_an_output_without_a_target_stays_valid(tmp_path: Path) -> None:
    """Most outputs are blackboard values, not files; absence must stay legal."""
    root = _skill(tmp_path / "absent", "")

    assert _compile_issues(root) == []
