"""A run keeps one identity and one directory, alive or dead.

Reproduces the 2026-08-16 field failure: a real run of
``story-deconstruction-v3-lab`` died at phase 23 and its evidence split in two.
``runs/485af68a-.../`` held the 1.4 MB ``trace.jsonl`` while
``runs/a7b0aeed-.../`` held ``result.json`` + ``metrics.json`` +
``final_state.json``, and that ``result.json`` carried ``trace_path: null`` —
so at the exact moment the trace mattered most, nothing in the result pointed
at it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from graph_agent.core.runner import resume_skill, run_skill
from graph_agent.io.run_layout import runs_root


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_skill(root: Path, *, action_body: str) -> None:
    _write(
        root / "GRAPH.md",
        """---
schema_version: "v0.3.0"
name: run-identity
io:
  inputs:
    type: object
    properties:
      topic:
        type: string
    required: [topic]
  outputs:
    type: object
    properties:
      answer:
        type: string
phases:
  - draft
---
<phase depends_on="input" output>draft</phase>
""",
    )
    _write(
        root / "phases" / "draft" / "LOGIC.md",
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
      answer:
        type: string
---
<action>draft</action>
""",
    )
    _write(root / "phases" / "draft" / "actions" / "draft.py", action_body)


_DYING_ACTION = (
    "def draft(inputs):\n"
    "    raise ValueError('dynamic dimension must be snake_case')\n"
)

_LIVING_ACTION = (
    "def draft(inputs):\n"
    "    return {'answer': 'draft:' + str(inputs.get('topic', 'missing'))}\n"
)


def _run_dirs(workspace_dir: Path) -> list[str]:
    root = runs_root(workspace_dir)
    return sorted(child.name for child in root.iterdir() if child.is_dir())


def test_failed_run_without_thread_id_files_result_next_to_its_trace(
    tmp_path: Path,
    mock_skill_resolver: Any,
) -> None:
    skill_root = tmp_path / "skill"
    workspace_dir = tmp_path / "workspace"
    _write_skill(skill_root, action_body=_DYING_ACTION)

    result = run_skill(
        skill_root,
        workspace_dir=workspace_dir,
        skill_resolver=mock_skill_resolver,
        topic="alpha",
    )

    assert result.success is False
    # a. one run, one identity: the failed run minted exactly one directory.
    assert _run_dirs(workspace_dir) == [result.run_id]

    run_dir = runs_root(workspace_dir) / result.run_id
    # b. result and trace share that directory.
    assert (run_dir / "trace.jsonl").is_file()
    assert (run_dir / "result.json").is_file()

    # c. the failed result points at the trace that actually exists.
    assert result.trace_path is not None
    assert Path(result.trace_path) == run_dir / "trace.jsonl"

    persisted = json.loads((run_dir / "result.json").read_text(encoding="utf-8"))
    assert persisted["run_id"] == result.run_id
    assert Path(persisted["trace_path"]) == run_dir / "trace.jsonl"


def test_failed_run_with_thread_id_keeps_the_caller_identity(
    tmp_path: Path,
    mock_skill_resolver: Any,
) -> None:
    skill_root = tmp_path / "skill"
    workspace_dir = tmp_path / "workspace"
    _write_skill(skill_root, action_body=_DYING_ACTION)

    result = run_skill(
        skill_root,
        workspace_dir=workspace_dir,
        thread_id="caller-chosen-id",
        skill_resolver=mock_skill_resolver,
        topic="alpha",
    )

    assert result.success is False
    assert result.run_id == "caller-chosen-id"
    assert _run_dirs(workspace_dir) == ["caller-chosen-id"]

    run_dir = runs_root(workspace_dir) / "caller-chosen-id"
    assert (run_dir / "trace.jsonl").is_file()
    assert result.trace_path is not None
    assert Path(result.trace_path) == run_dir / "trace.jsonl"


def test_run_that_dies_before_a_trace_exists_reports_no_trace_path(
    tmp_path: Path,
    mock_skill_resolver: Any,
) -> None:
    """A missing GRAPH.md is rejected before any sink opens — say so, do not point at nothing."""
    skill_root = tmp_path / "not_a_v030_skill"
    skill_root.mkdir()
    workspace_dir = tmp_path / "workspace"

    result = run_skill(
        skill_root,
        workspace_dir=workspace_dir,
        skill_resolver=mock_skill_resolver,
    )

    assert result.success is False
    assert result.error is not None
    assert result.error.code == "[F-v3-graph-root-missing]"
    assert _run_dirs(workspace_dir) == [result.run_id]
    assert not (runs_root(workspace_dir) / result.run_id / "trace.jsonl").exists()
    assert result.trace_path is None


def test_successful_run_without_thread_id_keeps_one_identity(
    tmp_path: Path,
    mock_skill_resolver: Any,
) -> None:
    skill_root = tmp_path / "skill"
    workspace_dir = tmp_path / "workspace"
    _write_skill(skill_root, action_body=_LIVING_ACTION)

    result = run_skill(
        skill_root,
        workspace_dir=workspace_dir,
        skill_resolver=mock_skill_resolver,
        topic="alpha",
    )

    assert result.success is True
    assert _run_dirs(workspace_dir) == [result.run_id]

    run_dir = runs_root(workspace_dir) / result.run_id
    assert (run_dir / "trace.jsonl").is_file()
    assert (run_dir / "result.json").is_file()
    assert result.trace_path is not None
    assert Path(result.trace_path) == run_dir / "trace.jsonl"


def test_successful_run_with_thread_id_keeps_the_caller_identity(
    tmp_path: Path,
    mock_skill_resolver: Any,
) -> None:
    skill_root = tmp_path / "skill"
    workspace_dir = tmp_path / "workspace"
    _write_skill(skill_root, action_body=_LIVING_ACTION)

    result = run_skill(
        skill_root,
        workspace_dir=workspace_dir,
        thread_id="caller-chosen-id",
        skill_resolver=mock_skill_resolver,
        topic="alpha",
    )

    assert result.success is True
    assert result.run_id == "caller-chosen-id"
    assert _run_dirs(workspace_dir) == ["caller-chosen-id"]
    assert result.trace_path is not None
    assert Path(result.trace_path) == runs_root(workspace_dir) / "caller-chosen-id" / "trace.jsonl"


def test_failed_resume_points_at_the_trace_it_opened(
    tmp_path: Path,
    mock_skill_resolver: Any,
) -> None:
    """``_resume_failed_result`` shares the disease: the sink is open, the pointer is None."""
    skill_root = tmp_path / "not_a_v030_skill"
    skill_root.mkdir()
    workspace_dir = tmp_path / "workspace"

    result = resume_skill(
        skill_root,
        workspace_dir=workspace_dir,
        run_id="resume-that-dies",
        skill_resolver=mock_skill_resolver,
    )

    assert result.success is False
    run_dir = runs_root(workspace_dir) / "resume-that-dies"
    assert (run_dir / "trace.jsonl").is_file()
    assert result.trace_path is not None
    assert Path(result.trace_path) == run_dir / "trace.jsonl"
