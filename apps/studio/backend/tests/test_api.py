from __future__ import annotations

import json
import queue
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from app.models.runs import RunMetadata
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
        "/api/skills/{skill_id}/fork",
        "/api/skills/{skill_id}/lint",
        "/api/skills/{skill_id}/runs",
        "/api/skills/{skill_id}/runs/batch-run",
        "/api/skills/{skill_id}/runs/{run_id}",
        "/api/skills/{skill_id}/runs/{run_id}/resume",
        "/api/skills/{skill_id}/terminal",
        "/api/skills/{skill_id}/test_inputs",
        "/api/skills/{skill_id}/test_inputs/{input_id}",
        "/api/skills/{skill_id}/golden",
        "/api/skills/{skill_id}/golden/{golden_id}",
        "/api/skills/{skill_id}/runs/{run_id}/compare",
        "/api/skills/{skill_id}/runs/{run_id}/diff",
        "/api/skills/{skill_id}/copilot/dispatch",
        "/api/skills/{skill_id}/runs/{run_id}/audit",
        "/api/batch/{batch_id}",
        "/api/templates",
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
    assert body["manifest"]["name"] == "text-segmentation"
    assert body["manifest"]["phases"][0]["id"] == "setup"
    assert body["graph_topology"] == [
        {"id": "setup", "src": "phases/setup", "depends_on": [], "mode": "logic"}
    ]
    assert set(body["node_schema_v21"]) == {"logic", "skill", "subgraph"}
    assert set(body["io_schema"]) == {"inputs", "outputs"}
    assert body["io_schema"]["inputs"]["properties"]["input_text"]["type"] == "string"
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
    skill_path = skill_dir / "phases" / "setup" / "LOGIC.md"
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


def test_put_single_file_edit_returns_v21_cutover_error(
    client: TestClient,
) -> None:
    response = client.put("/api/skills/text-segmentation", json={"content": "name: updated"})

    assert response.status_code == 422
    assert response.json()["error_code"] == "MANIFEST_VALIDATION_FAILED"
    assert response.json()["details"] == {"required_entry": "GRAPH.md"}


def test_create_skill_single_file_returns_v21_cutover_error(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/skills",
        json={"skill_id": "idea-generator", "content": _agent_skill_content("idea-generator")},
    )

    assert response.status_code == 422
    assert response.json()["details"] == {"required_entry": "GRAPH.md"}


def test_create_skill_collision_returns_409(client: TestClient) -> None:
    response = client.post(
        "/api/skills",
        json={"skill_id": "text-segmentation", "content": _agent_skill_content("text-segmentation")},
    )

    assert response.status_code == 409
    body = response.json()
    assert body["error_code"] == "SKILL_ALREADY_EXISTS"
    assert body["details"] == {"skill_id": "text-segmentation"}


@pytest.mark.xfail(reason="T3.1 PM decision: templates.py remains legacy parser follow-up")
def test_templates_api_lists_builtin_skill_templates(client: TestClient) -> None:
    response = client.get("/api/templates")

    assert response.status_code == 200
    templates = {item["id"]: item for item in response.json()}
    assert {"blank-agent", "blank-graph", "data-extractor", "chained-reasoning"} <= set(templates)
    assert templates["data-extractor"]["type"] == "graph"
    assert "extracted_data" in templates["data-extractor"]["content"]


def test_fork_skill_copies_directory_and_rewrites_identity(
    client: TestClient,
    studio_roots: tuple[Path, Path],
) -> None:
    skills_dir, workspaces_dir = studio_roots
    source_dir = skills_dir / "text-segmentation"
    (source_dir / "golden").mkdir()
    (source_dir / "golden" / "baseline.json").write_text('{"ok": true}', encoding="utf-8")

    response = client.post(
        "/api/skills/text-segmentation/fork",
        json={"new_skill_id": "text-segmentation-copy"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["id"] == "text-segmentation-copy"
    assert body["name"] == "text-segmentation-copy"

    target_dir = workspaces_dir / "default" / "skills" / "text-segmentation-copy"
    assert (target_dir / "GRAPH.md").exists()
    assert (target_dir / "phases" / "setup" / "actions" / "prepare.py").exists()
    assert (target_dir / "golden" / "baseline.json").exists()
    assert "name: text-segmentation-copy" in (target_dir / "GRAPH.md").read_text(encoding="utf-8")


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


def test_run_history_lists_details_and_deletes_runs(
    client: TestClient,
    studio_roots: tuple[Path, Path],
) -> None:
    _skills_dir, workspaces_dir = studio_roots
    older_dir = _write_run_record(
        workspaces_dir,
        "text-segmentation",
        "older-run",
        started_at=datetime.now(UTC) - timedelta(minutes=5),
        input_data={"chapter": "001", "count": 5, "extra": True},
    )
    newer_dir = _write_run_record(
        workspaces_dir,
        "text-segmentation",
        "newer-run",
        started_at=datetime.now(UTC),
        input_data={"chapter": "002"},
    )

    list_response = client.get("/api/skills/text-segmentation/runs")

    assert list_response.status_code == 200
    body = list_response.json()
    assert body["total"] == 2
    assert [item["run_id"] for item in body["runs"]] == ["newer-run", "older-run"]
    assert body["runs"][1]["input_summary"] == "chapter=001, count=5, +1"

    detail_response = client.get("/api/skills/text-segmentation/runs/older-run")

    assert detail_response.status_code == 200
    assert detail_response.json()["input_data"] == {"chapter": "001", "count": 5, "extra": True}

    delete_response = client.delete("/api/skills/text-segmentation/runs/older-run")

    assert delete_response.status_code == 204
    assert not older_dir.exists()
    assert newer_dir.exists()


def test_batch_run_starts_runs_from_test_inputs(
    client: TestClient,
    studio_roots: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    skills_dir, workspaces_dir = studio_roots
    skill_dir = copy_skill(skills_dir, workspaces_dir, "text-segmentation")
    inputs_dir = skill_dir / "test_inputs"
    inputs_dir.mkdir()
    for index in range(3):
        (inputs_dir / f"case-{index}.json").write_text(
            json.dumps({"input_text": f"hello {index}"}),
            encoding="utf-8",
        )
    monkeypatch.setattr(run_manager, "process_factory", InlineProcess)
    monkeypatch.setattr(run_manager, "queue_factory", queue.Queue)
    monkeypatch.setattr(run_manager, "worker", fake_run_worker)

    inputs_response = client.get("/api/skills/text-segmentation/test_inputs")

    assert inputs_response.status_code == 200
    assert [item["id"] for item in inputs_response.json()] == ["case-0", "case-1", "case-2"]

    batch_response = client.post(
        "/api/skills/text-segmentation/runs/batch-run",
        json={"input_ids": ["case-0", "case-1", "case-2"]},
    )

    assert batch_response.status_code == 202
    body = batch_response.json()
    assert body["batch_id"].startswith("batch-")
    assert len(body["sub_run_ids"]) == 3

    status = client.get(f"/api/batch/{body['batch_id']}").json()

    assert status["total"] == 3
    assert 0 <= status["completed"] <= 3
    assert [item["input_id"] for item in status["items"]] == ["case-0", "case-1", "case-2"]


def test_set_golden_and_compare_run_diff(
    client: TestClient,
    studio_roots: tuple[Path, Path],
) -> None:
    _skills_dir, workspaces_dir = studio_roots
    _write_final_state(
        workspaces_dir,
        "text-segmentation",
        "golden-run",
        {"answer": "hello world", "score": 10, "ok": True},
    )
    _write_final_state(
        workspaces_dir,
        "text-segmentation",
        "current-run",
        {"answer": "hello studio", "score": 8, "ok": False},
    )

    promote_response = client.post(
        "/api/skills/text-segmentation/golden",
        json={"run_id": "golden-run", "lock": False},
    )

    assert promote_response.status_code == 200
    assert promote_response.json()["id"] == "golden-run"

    diff_response = client.get(
        "/api/skills/text-segmentation/runs/current-run/diff?against=golden-run",
    )

    assert diff_response.status_code == 200
    body = diff_response.json()
    assert body["golden_run_id"] == "golden-run"
    assert body["total_score"] < 100
    answer_diff = next(
        item for item in body["differences"] if item["field_path"] == "output.answer"
    )
    assert answer_diff["type"] == "text"
    assert answer_diff["changed"] is True
    assert answer_diff["score"] < 1


def test_compare_missing_golden_returns_404(
    client: TestClient,
    studio_roots: tuple[Path, Path],
) -> None:
    _skills_dir, workspaces_dir = studio_roots
    _write_final_state(workspaces_dir, "text-segmentation", "current-run", {"answer": "hello"})

    response = client.get("/api/skills/text-segmentation/runs/current-run/diff")

    assert response.status_code == 404
    assert response.json()["error_code"] == "RESUME_CHECKPOINT_NOT_FOUND"


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
    response = client.delete("/api/skills/demo/golden/example")

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


def _write_final_state(
    workspaces_dir: Path,
    skill_id: str,
    run_id: str,
    payload: dict[str, Any],
) -> Path:
    run_dir = workspaces_dir / "default" / "skills" / skill_id / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "final_state.json").write_text(json.dumps(payload), encoding="utf-8")
    return run_dir


def _write_run_record(
    workspaces_dir: Path,
    skill_id: str,
    run_id: str,
    *,
    started_at: datetime,
    input_data: dict[str, Any],
) -> Path:
    run_dir = _write_final_state(workspaces_dir, skill_id, run_id, {"ok": True})
    metadata = RunMetadata(run_id=run_id, status="success", started_at=started_at)
    (run_dir / "run_metadata.json").write_text(metadata.model_dump_json(), encoding="utf-8")
    (run_dir / "input_data.json").write_text(json.dumps(input_data), encoding="utf-8")
    return run_dir
