from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def test_studio_queue_callback_serializes_a_gateway_route_decision() -> None:
    """The gateway's events carry no Pydantic, and still have to cross a process."""
    from app.services.run_manager import _queue_event_subscriber
    from graph_agent_gateway.events import LLMRouteDecisionEvent

    class RecordingQueue:
        def __init__(self) -> None:
            self.items: list[dict[str, object]] = []

        def put(self, item: dict[str, object]) -> None:
            self.items.append(item)

    queue = RecordingQueue()
    subscriber = _queue_event_subscriber(queue)

    subscriber(
        LLMRouteDecisionEvent(
            phase_name="e2e",
            decision="fell_back",
            route_id="primary:route",
            endpoint_id="primary",
            provider_model_id="gpt-5",
            protocol="openai_compatible",
            reason="RuntimeError: probe failed",
            provider_status_code=404,
            next_route_id="fallback:route",
            voided_streamed_answer=True,
        )
    )

    assert queue.items == [
        {
            "type": "event",
            "event": {
                "event_type": "llm_route_decision",
                "phase_name": "e2e",
                "decision": "fell_back",
                "route_id": "primary:route",
                "endpoint_id": "primary",
                "provider_model_id": "gpt-5",
                "protocol": "openai_compatible",
                "reason": "RuntimeError: probe failed",
                "provider_status_code": 404,
                "next_route_id": "fallback:route",
                "voided_streamed_answer": True,
                "code": "[F-v3-gateway-llm-route-decision]",
            },
        }
    ]


def test_trace_jsonl_is_read_as_event_envelopes(tmp_path: Path) -> None:
    from app.services.run_manager import _read_events

    trace_path = tmp_path / "trace.jsonl"
    trace_path.write_text(
        "\n".join(
            [
                (
                    '{"schema_version":"1.0","event_type":"phase_start",'
                    '"timestamp":"2026-06-17T00:00:00Z","phase_name":"draft"}'
                ),
                (
                    '{"schema_version":"1.0","event_type":"phase_end",'
                    '"timestamp":"2026-06-17T00:00:01Z","phase_name":"draft","status":"success"}'
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    events = _read_events(trace_path, run_id="run-1")

    assert [event.schema_version for event in events] == ["studio.event.v1", "studio.event.v1"]
    assert [event.seq for event in events] == [1, 2]
    assert [event.cursor for event in events] == ["run:run-1:1", "run:run-1:2"]
    assert [event.event_type for event in events] == ["phase_start", "phase_end"]
    assert events[0].payload["phase_name"] == "draft"


def test_run_worker_treats_artifact_error_result_as_failed_and_preserves_payload(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    import app.services.run_manager as run_manager_module
    from app.core.adapters.run_artifact_store_local import LocalRunArtifactStore
    from graph_agent.core.adapter_contracts import RunArtifactErrorResult

    class RecordingQueue:
        def __init__(self) -> None:
            self.items: list[dict[str, Any]] = []

        def put(self, item: dict[str, Any]) -> None:
            self.items.append(item)

    class FakeAdapter:
        transport = "in_process"

        def run_artifact(self, _payload: dict[str, Any]) -> RunArtifactErrorResult:
            return RunArtifactErrorResult(
                error_code="llm.provider_not_configured",
                error_payload={"message": "LLM Provider is not configured"},
                run_id="run-error-result",
                retryable=False,
            )

    monkeypatch.setattr(run_manager_module, "build_engine_adapter", lambda: FakeAdapter())

    run_dir = tmp_path / "skills" / "demo.skill" / ".workspace" / "runs" / "run-error-result"
    queue = RecordingQueue()

    run_manager_module._run_worker_main(
        "demo.skill",
        str(run_dir),
        {},
        queue,
        {
            "artifact_id": "demo.skill",
            "content_hash": f"sha256:{'1' * 64}",
            "store": "ephemeral",
            "manifest_ref": "manifests/demo.skill.json",
        },
    )

    assert queue.items[-1]["type"] == "status"
    assert queue.items[-1]["status"] == "failed"
    # The worker normalizes every failure shape into one RunError before it leaves
    # the child; the artifact envelope's code and message must both survive that.
    assert queue.items[-1]["error"] == {
        "code": "llm.provider_not_configured",
        "message": "LLM Provider is not configured",
        "details": {},
    }

    store = LocalRunArtifactStore(root=run_dir.parent.parent)
    final_state = json.loads(store.get_run_object("run-error-result", "final_state.json").decode("utf-8"))
    assert final_state == {
        "error_code": "llm.provider_not_configured",
        "error_payload": {"message": "LLM Provider is not configured"},
        "run_id": "run-error-result",
        "retryable": False,
    }


def test_run_worker_persists_sealed_result_snapshot_and_per_node_outputs(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    import app.services.run_manager as run_manager_module
    from app.core.adapters.run_artifact_store_local import LocalRunArtifactStore
    from graph_agent.core.result_contracts import RunResultSnapshot

    class RecordingQueue:
        def __init__(self) -> None:
            self.items: list[dict[str, Any]] = []

        def put(self, item: dict[str, Any]) -> None:
            self.items.append(item)

    class FakeAdapter:
        transport = "in_process"

        def run_artifact(self, _payload: dict[str, Any]) -> dict[str, Any]:
            return {
                "success": True,
                "run_id": "run-result-snapshot",
                "skill_id": "demo.skill",
                "context": {
                    "phase_outputs": {
                        "draft": {"answer": "sealed draft"},
                        "review": {"review": "approved"},
                    }
                },
                "metrics": {"total_tokens": 11},
            }

    monkeypatch.setattr(run_manager_module, "build_engine_adapter", lambda: FakeAdapter())

    run_dir = tmp_path / "skills" / "demo.skill" / ".workspace" / "runs" / "run-result-snapshot"
    queue = RecordingQueue()

    run_manager_module._run_worker_main(
        "demo.skill",
        str(run_dir),
        {},
        queue,
        {
            "artifact_id": "demo.skill",
            "content_hash": f"sha256:{'2' * 64}",
            "store": "ephemeral",
            "manifest_ref": "manifests/demo.skill.json",
        },
    )

    store = LocalRunArtifactStore(root=run_dir.parent.parent)
    snapshot_payload = json.loads(store.get_run_object("run-result-snapshot", "result.json").decode("utf-8"))
    snapshot = RunResultSnapshot.model_validate(snapshot_payload)

    assert snapshot.run_results_ref.uri == "demo.skill/runs/run-result-snapshot/result.json"
    assert snapshot.status == "success"
    assert [node.agent_node_id for node in snapshot.node_results] == ["draft", "review"]
    assert [node.outputs_ref for node in snapshot.node_results] == [
        "demo.skill/runs/run-result-snapshot/nodes/draft/outputs.json",
        "demo.skill/runs/run-result-snapshot/nodes/review/outputs.json",
    ]
    draft_output = json.loads(
        store.get_run_object("run-result-snapshot", "nodes/draft/outputs.json").decode("utf-8")
    )
    review_output = json.loads(
        store.get_run_object("run-result-snapshot", "nodes/review/outputs.json").decode("utf-8")
    )
    assert draft_output == {"answer": "sealed draft"}
    assert review_output == {"review": "approved"}
