"""E2E RED coverage for WS-E7 golden evaluation and resume."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from textwrap import dedent
from typing import Any

import graph_agent
from graph_agent.core.checkpointer import get_checkpointer, reset_checkpointer
from graph_agent.core.runner import run_skill


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    _write(path, json.dumps(payload, ensure_ascii=False, indent=2))


def _public_callable(name: str) -> Callable[..., Any]:
    value = getattr(graph_agent, name, None)
    assert callable(value), f"graph_agent.{name} must be a public callable"
    return value


def _schema(properties: dict[str, Any], *, required: list[str] | None = None) -> str:
    payload: dict[str, Any] = {"type": "object", "properties": properties}
    if required is not None:
        payload["required"] = required
    return json.dumps(payload, ensure_ascii=False, indent=4).replace("\n", "\n    ")


def _skill(root: Path) -> None:
    graph_input = _schema({"topic": {"type": "string"}}, required=["topic"])
    graph_output = _schema(
        {
            "draft": {"type": "string"},
            "final": {"type": "string"},
        },
        required=["draft", "final"],
    )
    _write(
        root / "GRAPH.md",
        f"""---
schema_version: "v0.3.0"
name: ws-e7-golden-resume-e2e
io:
  inputs:
    {graph_input}
  outputs:
    {graph_output}
phases:
  - draft
  - finish
---
<phase depends_on="input">draft</phase>
<phase depends_on="draft" output>finish</phase>
""",
    )
    _write(
        root / "phases" / "draft" / "LOGIC.md",
        f"""---
io:
  inputs:
    {graph_input}
  outputs:
    {_schema({"draft": {"type": "string"}}, required=["draft"])}
actions: [draft]
validator: false
---
<action>draft</action>
""",
    )
    _write(
        root / "phases" / "draft" / "actions" / "draft.py",
        dedent(
            """
            def draft(context):
                return {"draft": f"draft:{context['topic']}"}
            """
        ).lstrip(),
    )
    _write(
        root / "phases" / "finish" / "LOGIC.md",
        f"""---
io:
  inputs:
    {_schema({"draft": {"type": "string"}}, required=["draft"])}
  outputs:
    {_schema({"final": {"type": "string"}}, required=["final"])}
actions: [finish]
validator: false
---
<action>finish</action>
""",
    )
    _write(
        root / "phases" / "finish" / "actions" / "finish.py",
        dedent(
            """
            def finish(context):
                return {"final": f"final:{context['draft']}"}
            """
        ).lstrip(),
    )


def _checkpoint_id_with_draft_without_final(run_id: str) -> str:
    saver = get_checkpointer()
    for checkpoint in saver.list({"configurable": {"thread_id": run_id, "checkpoint_ns": ""}}):
        values = checkpoint.checkpoint.get("channel_values", {})
        data = values.get("data")
        if hasattr(data, "model_dump"):
            data = data.model_dump()
        if isinstance(data, dict) and "draft" in data and "final" not in data:
            return str(checkpoint.checkpoint["id"])
    raise AssertionError("expected a checkpoint after draft and before finish")


def test_ws_e7_golden_report_and_resume_share_workspace_run_contract(
    tmp_path: Path,
    mock_skill_resolver: object,
) -> None:
    skill_root = tmp_path / "skill"
    workspace_dir = tmp_path / "workspace"
    baseline_id = "baseline-e2e"
    run_id = "ws-e7-e2e-run"
    _skill(skill_root)
    _write_json(
        workspace_dir / "golden" / baseline_id / "baseline.json",
        {"baseline_id": baseline_id, "case_ids": ["case-e2e"]},
    )
    _write_json(
        workspace_dir / "golden" / baseline_id / "cases" / "case-e2e.json",
        {
            "case_id": "case-e2e",
            "phase_id": "draft",
            "inputs": {"topic": "alpha"},
            "expected_output": {"draft": "draft:alpha"},
            "source": "manual",
            "updated_at": "2026-06-10T00:00:00Z",
        },
    )

    reset_checkpointer()
    try:
        initial = run_skill(
            skill_root,
            workspace_dir=workspace_dir,
            thread_id=run_id,
            cleanup_checkpoints_on_finish=False,
            skill_resolver=mock_skill_resolver,
            topic="alpha",
        )
        assert initial.success is True
        checkpoint_id = _checkpoint_id_with_draft_without_final(run_id)

        evaluate = _public_callable("evaluate_golden_baseline")
        resume_skill = _public_callable("resume_skill")

        report = evaluate(
            skill_root,
            workspace_dir=workspace_dir,
            baseline_id=baseline_id,
            skill_resolver=mock_skill_resolver,
        )
        if hasattr(report, "model_dump"):
            report = report.model_dump(mode="json")

        resumed = resume_skill(
            skill_root,
            workspace_dir=workspace_dir,
            run_id=run_id,
            checkpoint_id=checkpoint_id,
            context_overrides={"draft": "draft:manual"},
            skill_resolver=mock_skill_resolver,
        )

        assert report["summary"]["passed"] == 1
        assert (workspace_dir / "golden" / baseline_id / "report.json").is_file()
        assert resumed.run_id == run_id
        assert resumed.context["final"] == "final:draft:manual"
        assert (workspace_dir / "runs" / run_id / "result.json").is_file()
        assert not (workspace_dir / "predict" / "latest_predict.json").exists()
        assert not list(skill_root.rglob("golden.json"))
    finally:
        reset_checkpointer()
