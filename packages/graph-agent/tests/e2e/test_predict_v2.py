from __future__ import annotations

import json
from pathlib import Path

import pytest
from graph_agent import run_skill
from graph_agent.core import runner as runner_module
from graph_agent.core._predict_internal.interception import PredictGatewayChatModel
from graph_agent.core._predict_internal.tracing import (
    PredictTracingCallback,
    clear_mock_source_cache,
)
from graph_agent.models.gateway_chat_model import GatewayChatModel


def test_p2_predict_run_completes_logic_and_llm_graph_without_provider(tmp_path: Path) -> None:
    skill_path = _write_predict_skill(tmp_path)

    result, callback = _run_predict(skill_path, None)

    assert result.success is True
    assert result.context["prepared"] is True
    assert [phase["name"] for phase in callback.phases] == ["prepare", "draft"]
    assert callback.phases[0].get("mocked_source") is None
    assert callback.phases[1]["mocked_source"] == "heuristic_stub"
    assert callback.summary()["total_input_tokens"] == 0
    assert callback.summary()["total_output_tokens"] == 0


@pytest.mark.parametrize(
    ("mock_llm", "expected_source"),
    [
        ({"draft": {"text": "manual draft"}}, "manual"),
        ({"draft": {"source": "copilot", "output": {"text": "copilot draft"}}}, "copilot"),
    ],
)
def test_p1_predict_run_uses_dict_override_source(
    tmp_path: Path,
    mock_llm: dict[str, object],
    expected_source: str,
) -> None:
    skill_path = _write_predict_skill(tmp_path)

    result, callback = _run_predict(skill_path, mock_llm)

    assert result.success is True
    assert callback.phases[1]["mocked_source"] == expected_source


def test_p0_predict_run_uses_golden_case_source(tmp_path: Path) -> None:
    skill_path = _write_predict_skill(tmp_path)
    golden_path = _write_golden_case(tmp_path, expected_path=["prepare", "draft"])

    result, callback = _run_predict(skill_path, golden_path)

    assert result.success is True
    assert callback.phases[1]["mocked_source"] == "golden_case"


def test_predict_run_does_not_leave_mock_binding_on_cached_harness(tmp_path: Path) -> None:
    skill_path = _write_predict_skill(tmp_path)
    runner_module.clear_cache()

    result, _callback = _run_predict(skill_path, None)

    assert result.success is True
    harness = runner_module._harness_cache[str(skill_path.resolve())][0]
    assert not hasattr(harness._resolver, "_graph_agent_predict_mock_strategy")
    model = harness._resolver.resolve("analyst", phase_name="draft")
    assert type(model) is GatewayChatModel
    assert not isinstance(model, PredictGatewayChatModel)


def _run_predict(
    skill_path: Path,
    mock_llm: object,
) -> tuple[object, PredictTracingCallback]:
    clear_mock_source_cache()
    callback = PredictTracingCallback()
    callback.on_chain_start(metadata={})
    result = run_skill(
        skill_path,
        mock_llm=mock_llm,
        callbacks=[callback],
        topic="mars",
        unattended=True,
        cleanup_checkpoints_on_finish=False,
    )
    return result, callback


def _write_predict_skill(tmp_path: Path) -> Path:
    script_dir = tmp_path / "script"
    script_dir.mkdir()
    (script_dir / "__init__.py").write_text("", encoding="utf-8")
    (script_dir / "logic.py").write_text(
        "def prepare(ctx):\n"
        "    ctx['prepared'] = True\n"
        "    return ctx\n",
        encoding="utf-8",
    )
    skill_path = tmp_path / "SKILL.md"
    skill_path.write_text(
        """---
schema_version: "2.0"
name: predict-e2e
version: "0.1"
description: Predict e2e smoke
type: graph
context_mapping:
  topic: "{input.topic}"
io:
  inputs:
    - name: topic
      type: str
      source: runtime
  outputs: []
phases:
  - name: prepare
    mode: logic
    execute_steps:
      - script.logic.prepare
  - name: draft
    mode: llm
    llm_role: analyst
    max_iterations: 1
    max_nudges: 0
    validator_optional: true
    output_schema: |
      text: str
    prompt: |
      Write a draft for {topic} and call finish_task.
---
""",
        encoding="utf-8",
    )
    return skill_path


def _write_golden_case(tmp_path: Path, *, expected_path: list[str]) -> Path:
    path = tmp_path / "case.golden.json"
    path.write_text(
        json.dumps(
            {
                "inputs": {"topic": "mars"},
                "metadata": {
                    "phase_name": "draft",
                    "prompt_hash": "old-prompt",
                    "io_outputs_schema_hash": "old-schema",
                    "expected_path": expected_path,
                },
                "expected_traces": {"draft": {"text": "golden draft"}},
            }
        ),
        encoding="utf-8",
    )
    return path
