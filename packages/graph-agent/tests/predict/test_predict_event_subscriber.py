from __future__ import annotations

from pathlib import Path
from typing import Any

from graph_agent.core import runner as runner_module
from graph_agent.core.adapter_contracts import PredictArtifactRequest
from graph_agent.core.artifacts import ArtifactRef
from graph_agent.core.result import RunResult


def test_sdk_predict_artifact_threads_event_subscriber_to_predict_skill(
    monkeypatch,
    tmp_path: Path,
    mock_skill_resolver: Any,
) -> None:
    skill_root = tmp_path / "artifact"
    workspace_dir = tmp_path / "workspace"

    def subscriber(_event: object) -> None:
        return None

    received: list[Any] = []

    def fake_predict_skill(*_args: Any, **kwargs: Any) -> RunResult:
        received.append(kwargs.get("event_subscriber"))
        return RunResult(
            success=True,
            run_id="predict-sdk-events",
            skill_id="artifact",
            context={},
            source="predict",
            phases=[],
        )

    monkeypatch.setattr(runner_module, "_resolve_artifact_root", lambda _request: skill_root)
    monkeypatch.setattr(runner_module, "_resolve_artifact_workspace_dir", lambda _request: workspace_dir)
    monkeypatch.setattr(runner_module, "predict_skill", fake_predict_skill)

    request = PredictArtifactRequest(
        artifact_ref=ArtifactRef(
            artifact_id="artifact",
            content_hash="sha256:" + "4" * 64,
            store="ephemeral",
            manifest_ref="manifest",
            source_map_ref="source-map",
        ),
        inputs={},
        execution_context={"event_subscriber": subscriber},
        idempotency_key="idem-sdk-events",
    )

    result = runner_module._run_compiled_artifact_predict_graph(
        request,
        run_id="predict-sdk-events",
        skill_resolver=mock_skill_resolver,
        llm_provider=None,
        model_resolver=None,
    )

    assert isinstance(result, RunResult)
    assert received == [subscriber]
