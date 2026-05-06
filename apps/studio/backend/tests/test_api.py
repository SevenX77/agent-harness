from __future__ import annotations

import json
import queue
from pathlib import Path
from typing import Any

import pytest
from app.services.event_bus import event_bus
from app.services.run_manager import run_manager
from app.services.terminal_manager import terminal_manager
from fastapi.testclient import TestClient

from graph_agent.callbacks.events import (
    FinishTaskEvent,
    LLMCallEvent,
    PhaseEndEvent,
    PhaseStartEvent,
    RunEndedEvent,
    RunStartedEvent,
)
from tests.conftest import copy_skill


def test_openapi_registers_phase0_rest_surface(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    expected_paths = {
        "/api/skills",
        "/api/skills/{skill_id}",
        "/api/skills/{skill_id}/lint",
        "/api/skills/{skill_id}/runs",
        "/api/skills/{skill_id}/runs/{run_id}",
        "/api/skills/{skill_id}/runs/{run_id}/resume",
        "/api/skills/{skill_id}/terminal",
        "/api/skills/{skill_id}/test_inputs",
        "/api/skills/{skill_id}/test_inputs/{input_id}",
        "/api/skills/{skill_id}/golden",
        "/api/skills/{skill_id}/golden/{golden_id}",
        "/api/skills/{skill_id}/runs/{run_id}/compare",
        "/api/skills/{skill_id}/copilot/dispatch",
        "/api/skills/{skill_id}/runs/{run_id}/audit",
    }

    assert expected_paths <= set(schema["paths"])
    assert "/api/_debug/value-error" not in schema["paths"]


def test_skills_list_and_detail_use_real_skill_files(client: TestClient) -> None:
    skills_response = client.get("/api/skills")
    assert skills_response.status_code == 200
    skill_ids = {item["id"] for item in skills_response.json()}
    assert {"text-segmentation", "event-extraction", "batch-analysis", "global-synthesis"} <= skill_ids

    detail_response = client.get("/api/skills/text-segmentation")
    assert detail_response.status_code == 200
    body = detail_response.json()
    assert body["manifest"]["type"] == "graph"
    assert body["manifest"]["io"]["inputs"][0]["name"] == "input_text"
    assert body["manifest"]["phases"][0]["name"] == "setup"
    assert body["lint_result"]["status"] == "passed"


def test_missing_skill_returns_standard_404(client: TestClient) -> None:
    response = client.get("/api/skills/nope")

    assert response.status_code == 404
    assert response.json()["error_code"] == "SKILL_NOT_FOUND"


def test_lint_reports_failed_manifest_with_line_number(
    client: TestClient,
    studio_roots: tuple[Path, Path],
) -> None:
    skills_dir, workspaces_dir = studio_roots
    skill_dir = copy_skill(skills_dir, workspaces_dir, "text-segmentation")
    skill_path = skill_dir / "SKILL.md"
    skill_path.write_text(
        skill_path.read_text(encoding="utf-8").replace("mode: logic\n", "mode: bogus\n"),
        encoding="utf-8",
    )

    response = client.post("/api/skills/text-segmentation/lint")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "failed"
    assert body["errors"][0]["line"] is not None
    assert body["errors"][0]["error_code"]


def test_put_updates_workspace_atomically_and_invalid_content_preserves_file(
    client: TestClient,
    studio_roots: tuple[Path, Path],
) -> None:
    skills_dir, workspaces_dir = studio_roots
    original = (skills_dir / "text-segmentation" / "SKILL.md").read_text(encoding="utf-8")
    updated = original.replace("description: Text segments", "description: Updated text segments")

    ok_response = client.put("/api/skills/text-segmentation", json={"content": updated})

    assert ok_response.status_code == 200
    assert ok_response.json()["manifest"]["description"] == "Updated text segments"
    workspace_skill = workspaces_dir / "default" / "skills" / "text-segmentation" / "SKILL.md"
    assert "Updated text segments" in workspace_skill.read_text(encoding="utf-8")

    bad_response = client.put("/api/skills/text-segmentation", json={"content": "not yaml"})

    assert bad_response.status_code == 422
    assert "Updated text segments" in workspace_skill.read_text(encoding="utf-8")


def test_create_skill_writes_workspace_skill_and_summary(
    client: TestClient,
    studio_roots: tuple[Path, Path],
) -> None:
    _skills_dir, workspaces_dir = studio_roots

    response = client.post(
        "/api/skills",
        json={"skill_id": "idea-generator", "content": _agent_skill_content("idea-generator")},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["id"] == "idea-generator"
    assert body["name"] == "idea-generator"
    assert body["description"] == "Draft structured ideas"
    assert body["phase_count"] == 1

    skill_dir = workspaces_dir / "default" / "skills" / "idea-generator"
    assert (skill_dir / "SKILL.md").exists()
    assert (skill_dir / "skill_summary.json").exists()


def test_create_skill_collision_returns_409(client: TestClient) -> None:
    response = client.post(
        "/api/skills",
        json={"skill_id": "text-segmentation", "content": _agent_skill_content("text-segmentation")},
    )

    assert response.status_code == 409
    body = response.json()
    assert body["error_code"] == "SKILL_ALREADY_EXISTS"
    assert body["details"] == {"skill_id": "text-segmentation"}


def test_request_validation_errors_use_error_response(client: TestClient) -> None:
    response = client.post("/api/skills/demo/runs", json={"unexpected": "field"})

    assert response.status_code == 422
    body = response.json()
    assert body["error_code"] == "MANIFEST_VALIDATION_FAILED"
    assert body["http_status"] == 422
    assert body["retry_strategy"] == "not_retryable"
    assert body["details"]["errors"]


def test_run_endpoint_spawns_worker_and_ws_streams_events(
    client: TestClient,
    studio_roots: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _skills_dir, workspaces_dir = studio_roots
    monkeypatch.setattr(run_manager, "process_factory", InlineProcess)
    monkeypatch.setattr(run_manager, "queue_factory", queue.Queue)
    monkeypatch.setattr(run_manager, "worker", fake_run_worker)

    response = client.post(
        "/api/skills/text-segmentation/runs",
        json={"input_data": {"input_text": "hello"}},
    )

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "running"
    run_id = body["run_id"]

    with client.websocket_connect(f"/ws/runs/{run_id}") as websocket:
        event_types = [websocket.receive_json()["event_type"] for _ in range(6)]
    assert event_types == [
        "run_started",
        "phase_start",
        "llm_call",
        "phase_end",
        "finish_task",
        "run_ended",
    ]

    detail = client.get(f"/api/skills/text-segmentation/runs/{run_id}").json()
    assert detail["metadata"]["status"] == "success"
    run_dir = workspaces_dir / "default" / "skills" / "text-segmentation" / "runs" / run_id
    assert (run_dir / "final_state.json").exists()
    assert (run_dir / "tracing.jsonl").exists()
    assert (run_dir / "metrics.json").exists()
    assert (run_dir / "artifacts").is_dir()
    assert (run_dir / "checkpoints.db").exists()


def test_run_spawn_failure_maps_to_500(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(run_manager, "process_factory", FailingProcess)
    monkeypatch.setattr(run_manager, "queue_factory", queue.Queue)

    response = client.post(
        "/api/skills/text-segmentation/runs",
        json={"input_data": {"input_text": "hello"}},
    )

    assert response.status_code == 500
    assert response.json()["error_code"] == "RUN_SPAWN_FAILED"


def test_terminal_endpoint_spawns_pty_and_reaps_expired_session(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.services.terminal_manager.PtyProcess", FakePtyFactory)

    response = client.post("/api/skills/text-segmentation/terminal")

    assert response.status_code == 201
    body = response.json()
    assert body["ws_url"] == f"/ws/terminal/{body['term_id']}"
    with client.websocket_connect(body["ws_url"]) as websocket:
        assert websocket.receive_text() == "claude>"
        websocket.send_text("help\n")
    record = terminal_manager._sessions[body["term_id"]]
    record.expires_at = 0
    terminal_manager.reap_expired()
    assert body["term_id"] not in terminal_manager._sessions


def test_events_ws_broadcasts_to_multiple_clients(client: TestClient) -> None:
    with (
        client.websocket_connect("/ws/events") as first,
        client.websocket_connect("/ws/events") as second,
    ):
        event_bus.broadcast_from_thread({"type": "skill_changed", "skill_id": "text-segmentation"})
        assert first.receive_json() == {"type": "skill_changed", "skill_id": "text-segmentation"}
        assert second.receive_json() == {"type": "skill_changed", "skill_id": "text-segmentation"}


def test_deferred_endpoints_return_structured_501(client: TestClient) -> None:
    response = client.get("/api/skills/demo/golden")

    assert response.status_code == 501
    body = response.json()
    assert body["error_code"] == "NOT_IMPLEMENTED"
    assert body["http_status"] == 501
    assert body["retry_strategy"] == "not_retryable"


def test_value_error_handler_returns_studio_error_response(client: TestClient) -> None:
    response = client.get("/api/_debug/value-error")

    assert response.status_code == 422
    body = response.json()
    assert body == {
        "error_code": "MANIFEST_VALIDATION_FAILED",
        "http_status": 422,
        "message": "Studio debug ValueError",
        "details": None,
        "retry_strategy": "not_retryable",
    }


def test_cors_allows_vite_and_backup_dev_origins(client: TestClient) -> None:
    for origin in ("http://localhost:5173", "http://localhost:3000"):
        response = client.options(
            "/api/skills",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "GET",
            },
        )
        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == origin


class InlineProcess:
    def __init__(self, *, target: Any, args: tuple[Any, ...]) -> None:
        self._target = target
        self._args = args
        self.exitcode: int | None = None
        self._alive = False

    def start(self) -> None:
        self._alive = True
        self._target(*self._args)
        self.exitcode = 0
        self._alive = False

    def is_alive(self) -> bool:
        return self._alive

    def join(self, timeout: float | None = None) -> None:
        del timeout

    def terminate(self) -> None:
        self._alive = False


class FailingProcess(InlineProcess):
    def start(self) -> None:
        raise OSError("spawn denied")


def fake_run_worker(
    skill_id: str,
    skill_path_raw: str,
    run_dir_raw: str,
    inputs: dict[str, Any],
    process_queue: queue.Queue[dict[str, Any]],
) -> None:
    del skill_path_raw, inputs
    run_dir = Path(run_dir_raw)
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "artifacts").mkdir(exist_ok=True)
    events = [
        RunStartedEvent(run_id=run_dir.name, thread_id="thread", initial_context={}),
        PhaseStartEvent(phase_name="setup", context={}),
        LLMCallEvent(phase_name="setup", input_tokens=1, output_tokens=2),
        PhaseEndEvent(phase_name="setup", context={}, metrics={}),
        FinishTaskEvent(phase_name="setup", reasoning="done"),
        RunEndedEvent(
            run_id=run_dir.name,
            thread_id="thread",
            final_context={"skill_id": skill_id},
            wall_time_seconds=0.1,
        ),
    ]
    (run_dir / "tracing.jsonl").write_text(
        "\n".join(event.model_dump_json() for event in events) + "\n",
        encoding="utf-8",
    )
    (run_dir / "final_state.json").write_text(json.dumps({"ok": True}), encoding="utf-8")
    (run_dir / "metrics.json").write_text(json.dumps({"status": "success"}), encoding="utf-8")
    (run_dir / "checkpoints.db").touch()
    for event in events:
        process_queue.put({"type": "event", "event": event.model_dump(mode="json")})
    process_queue.put({"type": "status", "status": "success", "metrics": {}})


class FakePty:
    def __init__(self) -> None:
        self.terminated = False

    def read_nonblocking(self, size: int = 4096, timeout: float = 0.1) -> str | None:
        del size, timeout
        return "claude>"

    def write(self, data: object) -> None:
        del data

    def terminate(self, force: bool = False) -> None:
        del force
        self.terminated = True


class FakePtyFactory:
    @staticmethod
    def spawn(command: list[str], cwd: str) -> FakePty:
        del command, cwd
        return FakePty()


def _agent_skill_content(skill_id: str) -> str:
    return f"""---
schema_version: "2.0"
name: {skill_id}
description: Draft structured ideas
type: agent
context_mapping:
  topic: "{{input.topic}}"
agent_profile:
  role: Creative assistant
  goal: Generate concise planning ideas
  steps:
    - Read the requested topic
    - Return a short list of ideas
  constraints:
    - Keep the answer concise
  llm_role: analyst
user_prompt_template: |
  Generate ideas for {{topic}}.
---

# {skill_id}
"""
