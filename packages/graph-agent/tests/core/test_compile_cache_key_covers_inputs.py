"""A cached compile must not answer for a tree that is not the one on disk.

`compute_cache_key` walked `GRAPH.md` plus `phases/**/*.md` only. A skill with
nested subgraphs keeps most of its phases under `subgraph/**`, and every
validator / logic action is a `.py`. Those files ARE compile inputs — breaking
one changes the diagnostics — but they were outside the key, so `compile_skill`
served the previous tree's result and reported a clean compile for a broken
skill.

Direction of the error matters: an over-broad input set only costs an extra
recompile, while a too-narrow one produces a wrong answer. Build caches that
get this right (ccache, Bazel) all treat an unsound dependency set as a
correctness bug, not a tuning knob.

Measured on 2026-08-15 with `story-deconstruction-v3-lab`: 5 of its 133 `.md`
files and 0 of its 27 `.py` files were in the key. Breaking a subgraph phase
returned `issues=0`; bumping the root `GRAPH.md` mtime with the SAME broken
content returned 7 issues.
"""

from __future__ import annotations

from pathlib import Path

from graph_agent.core.cache import compute_cache_key

_GRAPH_MD = """---
schema_version: "v0.3.0"
name: cache-key-fixture
description: fixture
io:
  inputs:
    type: object
    required: [topic]
    properties:
      topic: {type: string}
  outputs:
    type: object
    required: [answer]
    properties:
      answer: {type: string}
phases:
  - main
---

<phase depends_on="input" output>main</phase>
"""

_PHASE_MD = """---
llm_role: analyst
io:
  inputs:
    type: object
    required: [topic]
    properties:
      topic: {type: string}
  outputs:
    type: object
    required: [answer]
    properties:
      answer: {type: string}
---

<role>fixture</role>
<goal>answer {topic}</goal>
"""


def _skill(tmp_path: Path) -> Path:
    root = tmp_path / "skill"
    (root / "phases" / "main").mkdir(parents=True)
    (root / "GRAPH.md").write_text(_GRAPH_MD, encoding="utf-8")
    (root / "phases" / "main" / "SKILL.md").write_text(_PHASE_MD, encoding="utf-8")

    nested = root / "subgraph" / "inner" / "phases" / "step"
    nested.mkdir(parents=True)
    (root / "subgraph" / "inner" / "GRAPH.md").write_text(_GRAPH_MD, encoding="utf-8")
    (nested / "SKILL.md").write_text(_PHASE_MD, encoding="utf-8")

    (root / "phases" / "main" / "validator.py").write_text(
        "def validate(output, state_slice, **kwargs):\n    return output\n",
        encoding="utf-8",
    )
    return root


def test_editing_a_subgraph_phase_moves_the_cache_key(tmp_path: Path) -> None:
    root = _skill(tmp_path)
    before = compute_cache_key(root)

    nested_phase = root / "subgraph" / "inner" / "phases" / "step" / "SKILL.md"
    nested_phase.write_text(
        nested_phase.read_text(encoding="utf-8").replace("<role>fixture</role>", "<role>edited</role>"),
        encoding="utf-8",
    )

    assert compute_cache_key(root) != before, (
        "a nested-subgraph phase is a compile input; leaving it out of the key "
        "makes compile_skill answer for the previous tree"
    )


def test_editing_a_validator_moves_the_cache_key(tmp_path: Path) -> None:
    root = _skill(tmp_path)
    before = compute_cache_key(root)

    validator = root / "phases" / "main" / "validator.py"
    validator.write_text(
        "def validate(output, state_slice, **kwargs):\n    return {'answer': 'changed'}\n",
        encoding="utf-8",
    )

    assert compute_cache_key(root) != before, (
        "a validator is loaded at compile time; editing it must invalidate the cache"
    )


def test_an_unrelated_file_outside_the_input_set_does_not_move_the_key(tmp_path: Path) -> None:
    """Over-approximating is the safe direction, but not to the point of absurdity.

    Workspace state and caches are written *by* runs, not read by compile;
    keying on them would invalidate the cache after every run.
    """
    root = _skill(tmp_path)
    before = compute_cache_key(root)

    workspace = root / ".workspace" / "runs" / "r1"
    workspace.mkdir(parents=True)
    (workspace / "trace.jsonl").write_text("{}\n", encoding="utf-8")
    (workspace / "notes.md").write_text("# run notes\n", encoding="utf-8")

    assert compute_cache_key(root) == before
