from __future__ import annotations

from pathlib import Path
from typing import Any

from graph_agent.core import runner as runner_module
from graph_agent.core._predict_internal.strategy import HeuristicStubStrategy
from graph_agent.io.run_layout import runs_root


def _write_logic_skill(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "GRAPH.md").write_text(
        """---
schema_version: "v0.3.0"
name: contract_guard
io:
  inputs:
    type: object
    properties: {}
  outputs:
    type: object
    required: [text]
    properties:
      text:
        type: string
phases:
  - draft
---
<phase depends_on="input" output>draft</phase>
""",
        encoding="utf-8",
    )
    phase_dir = root / "phases" / "draft"
    actions_dir = phase_dir / "actions"
    actions_dir.mkdir(parents=True)
    (phase_dir / "LOGIC.md").write_text(
        """---
io:
  inputs:
    type: object
    properties: {}
  outputs:
    type: object
    required: [text]
    properties:
      text:
        type: string
actions: [draft]
validator: false
---
<action>draft</action>
""",
        encoding="utf-8",
    )
    (actions_dir / "draft.py").write_text(
        "def draft(inputs):\n"
        "    return {'text': 'hello'}\n",
        encoding="utf-8",
    )
    return root


def test_run_path_behavior_unchanged_after_predict_context_param(
    tmp_path: Path,
    mock_skill_resolver: Any,
) -> None:
    skill_root = _write_logic_skill(tmp_path / "skill")

    raw = runner_module._run_v030_skill_dict(
        skill_root,
        workspace_dir=tmp_path / "workspace-run",
        run_root=runs_root(tmp_path / "workspace-run"),
        thread_id="run-contract-guard",
        skill_resolver=mock_skill_resolver,
    )

    assert raw["run_id"] == "run-contract-guard"
    assert raw["context"]["text"] == "hello"
    assert Path(raw["trace_path"]).is_file()


def test_predict_result_shape_unchanged(
    monkeypatch,
    tmp_path: Path,
    mock_skill_resolver: Any,
) -> None:
    skill_root = _write_logic_skill(tmp_path / "skill")

    def fake_strategy_from_param(_param: Any) -> HeuristicStubStrategy:
        strategy = HeuristicStubStrategy()
        strategy.expected_path = ["draft"]  # type: ignore[attr-defined]
        return strategy

    monkeypatch.setattr(
        "graph_agent.core._predict_internal.strategy.MockStrategy.from_param",
        fake_strategy_from_param,
    )

    result = runner_module.predict_skill(
        skill_root,
        workspace_dir=tmp_path / "workspace-predict",
        thread_id="predict-contract-guard",
        skill_resolver=mock_skill_resolver,
    )

    assert result.source == "predict"
    assert result.run_id == "predict-contract-guard"
    assert result.phases is not None
    assert [phase.phase_name for phase in result.phases] == ["draft"]
    assert result.path_diff is not None
    assert result.path_diff.expected_path == ["draft"]
    assert result.path_diff.actual_path == ["draft"]
    assert result.path_diff.missing == []
    assert result.path_diff.extra == []
    assert result.path_diff.order_mismatch is False
