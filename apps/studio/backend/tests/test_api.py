from __future__ import annotations

import json
import queue
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from app.core import config
from app.models.runs import RunMetadata
from app.services.event_bus import event_bus
from app.services.predict_gate import record_predict_pass
from app.services.run_manager import run_manager
from app.services.skills import resolve_skill_dir
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
from graph_agent.core.result_contracts import NodeRunResult, RunResultSnapshot, RunResultsRef

from tests.conftest import copy_skill

FALLBACK_HEADERS = {"X-Studio-Write-Fallback": "browser"}


def _open_skills_into_index(dirs_by_id: dict[str, Path]) -> None:
    """Record folders in the native-fs skill index so Home (IDE model) lists them.

    Home does not auto-scan a bundled skills registry (01_init.md D11);
    a folder surfaces only after it is opened/imported, which the native-fs layer
    records as a skill-index entry. Tests simulate that open by writing the entry.
    """
    import asyncio

    from app.core.adapters.metadata_local import LocalJsonMetadataStore

    metadata = LocalJsonMetadataStore(
        global_config_dir=config.APP_SETTINGS_DIR,
    )

    async def _register() -> None:
        for skill_id, skill_dir in dirs_by_id.items():
            await metadata.save_skill_index_entry(
                skill_id,
                {"absolute_path": str(skill_dir), "l2_remote_url": ""},
            )

    asyncio.run(_register())


def _record_predict_pass(skill_id: str) -> None:
    """Satisfy the server-side predict-pass run prerequisite for a skill.

    Mirrors the real predict-then-run flow: a passing Predict records predict-pass
    bound to the compiled content_hash, which the run-spawn gate consumes after
    matching it against the freshly-compiled hash. Compiling here (as the real
    predict does) guarantees the recorded hash matches what start_run compiles.
    """
    from app.core.adapters.engine import EngineAdapter

    skill_dir = resolve_skill_dir(skill_id)
    adapter = EngineAdapter(transport="in_process")
    art_ref = adapter.compile(
        {"skill_dir": str(skill_dir), "skill_id": skill_id, "artifact_scope": "ephemeral"}
    )
    record_predict_pass(skill_dir, skill_id, "predict-fixture", content_hash=art_ref["content_hash"])


def test_openapi_registers_phase0_rest_surface(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    expected_paths = {
        "/api/skills",
        "/api/skills/{skill_id}",
        "/api/skills/{skill_id}/history",
        "/api/skills/{skill_id}/revert",
        "/api/skills/{skill_id}/sync",
        "/api/skills/{skill_id}/publish",
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
        "/api/settings",
        "/api/templates",
    }

    assert expected_paths <= set(schema["paths"])
    assert "/api/_debug/value-error" not in schema["paths"]


def test_openapi_declares_typed_resume_error_responses(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()

    responses = schema["paths"]["/api/skills/{skill_id}/runs/{run_id}/resume"]["post"]["responses"]

    for status_code in ("404", "409", "422"):
        assert status_code in responses
        assert responses[status_code]["content"]["application/json"]["schema"]["$ref"].endswith("/ErrorResponse")


def test_skill_detail_uses_real_skill_files(
    client: TestClient,
    studio_roots: tuple[Path, Path],
) -> None:
    # GET /api/skills/{id} detail compiles the real on-disk files of an opened skill
    # (IDE model, 01_init.md D11 无注册表 — no Python LIST aggregation).
    skills_dir, workspaces_dir = studio_roots
    _open_skills_into_index({"text-segmentation": skills_dir / "text-segmentation"})

    detail_response = client.get("/api/skills/text-segmentation")
    assert detail_response.status_code == 200
    body = detail_response.json()
    assert body["manifest"]["schema_version"] == "v0.3.0"
    assert body["io_schema"]["inputs"]["properties"]["input_text"]["type"] == "string"
    assert body["manifest"]["phases"][0] == "setup"
    assert "GRAPH.md" in body["files"]
    assert body["lint_result"]["status"] == "failed"
    assert body["lint_result"]["errors"] == [
        {
                "file": ".workspace/runtime_config.json",
            "line": None,
            "column": None,
            "error_code": "STUDIO_RUNTIME_INPUT_MISSING",
            "severity": "error",
            "message": (
                "Graph input schema requires runtime input field 'input_text', "
                "but runtime_config has no root import binding. Add a matching file under "
                ".workspace/import_files before predict/run."
            ),
            "phase_name": None,
            "field_path": "input_text",
                "source_path": ".workspace/runtime_config.json",
        }
    ]


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
        skill_path.read_text(encoding="utf-8").replace("---\n", "---\nmode: bogus\n", 1),
        encoding="utf-8",
    )

    response = client.post("/api/skills/text-segmentation/lint")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "failed"
    assert body["errors"][0]["line"] is not None
    assert body["errors"][0]["error_code"]


def test_lint_accepts_changed_markdown_body_without_writing_disk(
    client: TestClient,
    studio_roots: tuple[Path, Path],
) -> None:
    skills_dir, _workspaces = studio_roots
    skill_id = "text-segmentation"
    graph_path = skills_dir / skill_id / "GRAPH.md"
    original = graph_path.read_text(encoding="utf-8")
    broken_body = original.replace("name: text-segmentation\n", "")
    assert broken_body != original

    response = client.post(
        f"/api/skills/{skill_id}/lint",
        json={"markdown": broken_body},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "failed"
    assert body["errors"], "broken changed-markdown must surface a diagnostic"
    assert body["errors"][0]["error_code"].startswith("F-")
    # The unsaved body must never be persisted to the skill store on disk.
    assert graph_path.read_text(encoding="utf-8") == original


def test_lint_changed_markdown_passes_when_disk_would_fail(
    client: TestClient,
    studio_roots: tuple[Path, Path],
) -> None:
    """A clean unsaved body lints green even if the disk copy is broken."""
    skills_dir, workspaces_dir = studio_roots
    skill_id = "text-segmentation"
    skill_dir = copy_skill(skills_dir, workspaces_dir, skill_id)
    test_inputs_dir = skill_dir / ".workspace" / "import_files"
    test_inputs_dir.mkdir(parents=True)
    (test_inputs_dir / "case-a.json").write_text('{"input_text":"hello"}', encoding="utf-8")
    good_graph = (skill_dir / "GRAPH.md").read_text(encoding="utf-8")
    # Break the disk copy so a path-based lint would fail.
    (skill_dir / "GRAPH.md").write_text(
        good_graph.replace("name: text-segmentation\n", ""),
        encoding="utf-8",
    )

    response = client.post(
        f"/api/skills/{skill_id}/lint",
        json={"markdown": good_graph},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "passed"


def test_lint_accepts_runtime_config_root_text_input(
    client: TestClient,
    studio_roots: tuple[Path, Path],
) -> None:
    skills_dir, workspaces_dir = studio_roots
    skill_id = "text-segmentation"
    skill_dir = copy_skill(skills_dir, workspaces_dir, skill_id)
    inputs_dir = skill_dir / ".workspace" / "import_files"
    inputs_dir.mkdir(parents=True)
    (inputs_dir / "input_text.txt").write_text("hello", encoding="utf-8")

    response = client.post(f"/api/skills/{skill_id}/lint")

    assert response.status_code == 200
    assert response.json()["status"] == "passed"
    runtime_config = json.loads((skill_dir / ".workspace" / "runtime_config.json").read_text(encoding="utf-8"))
    assert runtime_config["inputs"]["active"]["root"]["input_text"]["value_type"] == "string"


def test_lint_without_body_still_lints_disk_path(
    client: TestClient,
    studio_roots: tuple[Path, Path],
) -> None:
    """No body falls back to linting the full on-disk skill path, including preflight."""
    response = client.post("/api/skills/text-segmentation/lint")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "failed"
    assert body["errors"][0]["file"] == ".workspace/runtime_config.json"
    assert body["errors"][0]["field_path"] == "input_text"
    assert body["errors"][0]["error_code"] == "STUDIO_RUNTIME_INPUT_MISSING"


def test_put_updates_indexed_skill_atomically_and_invalid_content_preserves_file(
    client: TestClient,
    studio_roots: tuple[Path, Path],
) -> None:
    _skills_dir, workspaces_dir = studio_roots
    create_response = client.post(
        "/api/skills",
        json={"skill_id": "idea-generator", "files": _agent_skill_files("idea-generator")},
    )
    assert create_response.status_code == 201
    skill_path = config.DEFAULT_SKILLS_ROOT / "idea-generator" / "GRAPH.md"
    updated = skill_path.read_text(encoding="utf-8").replace(
        "description: Draft structured ideas",
        "description: Updated ideas",
    )
    files = _agent_skill_files("idea-generator")
    files["GRAPH.md"] = updated

    ok_response = client.put("/api/skills/idea-generator", json={"files": files}, headers=FALLBACK_HEADERS)

    assert ok_response.status_code == 200
    assert ok_response.json()["manifest"]["description"] == "Updated ideas"
    assert "Updated ideas" in skill_path.read_text(encoding="utf-8")
    assert not (workspaces_dir / "default" / "skills" / "idea-generator" / "GRAPH.md").exists()

    bad_files = dict(files)
    bad_files["GRAPH.md"] = "not yaml"
    bad_response = client.put("/api/skills/idea-generator", json={"files": bad_files}, headers=FALLBACK_HEADERS)

    assert bad_response.status_code == 422
    assert "Updated ideas" in skill_path.read_text(encoding="utf-8")


def test_create_skill(
    client: TestClient,
    studio_roots: tuple[Path, Path],
) -> None:
    _skills_dir, workspaces_dir = studio_roots

    response = client.post(
        "/api/skills",
        json={"skill_id": "idea-generator", "files": _agent_skill_files("idea-generator")},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["id"] == "idea-generator"
    assert body["name"] == "idea-generator"
    assert body["description"] == "Draft structured ideas"
    assert body["phase_count"] == 1
    skill_dir = config.DEFAULT_SKILLS_ROOT / "idea-generator"
    assert body["directory_path"] == str(skill_dir)

    assert (skill_dir / "GRAPH.md").exists()
    assert (skill_dir / ".workspace").is_dir()
    assert (skill_dir / ".git").is_dir()
    assert (skill_dir / ".gitignore").read_text(encoding="utf-8").splitlines() == [
        "/.workspace/*",
        "!/.workspace/golden/",
        "/.workspace/local_settings.json",
    ]
    assert not (workspaces_dir / "default" / "skills" / "idea-generator" / "GRAPH.md").exists()
    index = json.loads(config.SKILL_INDEX_PATH.read_text(encoding="utf-8"))
    assert index["idea-generator"]["absolute_path"] == str(skill_dir)


def test_create_skill_with_directory_path_writes_to_user_dir(
    client: TestClient,
    studio_roots: tuple[Path, Path],
    tmp_path: Path,
) -> None:
    _skills_dir, workspaces_dir = studio_roots
    parent_dir = tmp_path / "external-skills"
    parent_dir.mkdir()
    skill_dir = parent_dir / "idea-generator"

    response = client.post(
        "/api/skills",
        json={
            "skill_id": "idea-generator",
            "files": _agent_skill_files("idea-generator"),
            "directory_path": str(skill_dir),
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["id"] == "idea-generator"
    assert body["directory_path"] == str(skill_dir)
    assert (skill_dir / "GRAPH.md").exists()
    assert (skill_dir / ".workspace").is_dir()
    assert (skill_dir / ".git").is_dir()
    assert not (workspaces_dir / "default" / "skills" / "idea-generator" / "GRAPH.md").exists()
    index = json.loads(config.SKILL_INDEX_PATH.read_text(encoding="utf-8"))
    assert index["idea-generator"]["absolute_path"] == str(skill_dir)


def test_create_skill_with_invalid_directory_path_returns_422(
    client: TestClient,
    tmp_path: Path,
) -> None:
    responses = [
        client.post(
            "/api/skills",
            json={
                "skill_id": "relative-path",
                "files": _agent_skill_files("relative-path"),
                "directory_path": "relative/path",
            },
        ),
        client.post(
            "/api/skills",
            json={
                "skill_id": "missing-parent",
                "files": _agent_skill_files("missing-parent"),
                "directory_path": str(tmp_path / "missing" / "missing-parent"),
            },
        ),
    ]

    for response in responses:
        assert response.status_code == 422
        assert response.json()["error_code"] == "INVALID_DIRECTORY_PATH"


def test_create_skill_directory_path_conflict_returns_409(
    client: TestClient,
    tmp_path: Path,
) -> None:
    skill_dir = tmp_path / "shared-skill-dir"

    first_response = client.post(
        "/api/skills",
        json={
            "skill_id": "first-skill",
            "files": _agent_skill_files("first-skill"),
            "directory_path": str(skill_dir),
        },
    )
    second_response = client.post(
        "/api/skills",
        json={
            "skill_id": "second-skill",
            "files": _agent_skill_files("second-skill"),
            "directory_path": str(skill_dir),
        },
    )

    assert first_response.status_code == 201
    assert second_response.status_code == 409
    assert second_response.json()["error_code"] == "SKILL_ALREADY_EXISTS"


def test_resolve_skill_dir_uses_directory_path_when_set(
    client: TestClient,
    tmp_path: Path,
) -> None:
    skill_dir = tmp_path / "external-skill"
    create_response = client.post(
        "/api/skills",
        json={
            "skill_id": "external-skill",
            "files": _agent_skill_files("external-skill"),
            "directory_path": str(skill_dir),
        },
    )

    detail_response = client.get("/api/skills/external-skill")

    assert create_response.status_code == 201
    assert detail_response.status_code == 200
    file_paths = detail_response.json()["file_paths"]
    assert file_paths["skill_dir"] == str(skill_dir)
    assert file_paths["graph_md"] == str(skill_dir / "GRAPH.md")
    assert file_paths["runs_dir"] == str(skill_dir / ".workspace" / "runs")
    assert file_paths["golden_dir"] == str(skill_dir / ".workspace" / "golden")
    assert "predict_dir" not in file_paths
    assert file_paths["local_settings"] == str(skill_dir / ".workspace" / "local_settings.json")


def test_create_skill_collision_returns_409(client: TestClient) -> None:
    response = client.post(
        "/api/skills",
        json={
            "skill_id": "text-segmentation",
            "files": _agent_skill_files("text-segmentation"),
        },
    )

    assert response.status_code == 409
    body = response.json()
    assert body["error_code"] == "SKILL_ALREADY_EXISTS"
    assert body["details"] == {"skill_id": "text-segmentation"}


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

    target_dir = skills_dir / "text-segmentation-copy"
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


@pytest.mark.parametrize(
    ("error_code", "payload", "expected_status"),
    [
        ("artifact.hash_mismatch", {"expected": "a", "actual": "b"}, 422),
        ("artifact.not_found", {"hash": "sha256:missing"}, 404),
    ],
)
def test_get_run_detail_maps_artifact_adapter_errors_to_typed_error_response(
    monkeypatch: pytest.MonkeyPatch,
    error_code: str,
    payload: dict[str, Any],
    expected_status: int,
) -> None:
    from app.core.adapters.http_transport import StudioAdapterError
    from app.main import create_app

    def raise_artifact_error(*_args: Any, **_kwargs: Any) -> None:
        raise StudioAdapterError(error_code, payload)

    monkeypatch.setattr(run_manager, "get_run_detail", raise_artifact_error)

    with TestClient(create_app(), raise_server_exceptions=False) as api_client:
        api_client.headers["Authorization"] = "Bearer studio-test-token"
        response = api_client.get("/api/skills/text-segmentation/runs/run-1")

    assert response.status_code == expected_status
    body = response.json()
    assert body["error_code"] == error_code
    assert body["http_status"] == expected_status
    assert body["details"] == payload


def test_resume_maps_runtime_state_adapter_errors_to_typed_error_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.core.adapters.transport_factory as transport_factory
    from app.core.adapters.http_transport import StudioAdapterError
    from app.main import create_app

    payload = {"run_id": "run-1", "active_owner": "worker-a"}

    class FakeAdapter:
        def resume(self, _payload: dict[str, Any]) -> dict[str, Any]:
            raise StudioAdapterError("state.lease_conflict", payload)

    monkeypatch.setattr(transport_factory, "build_engine_adapter", lambda: FakeAdapter())

    with TestClient(create_app(), raise_server_exceptions=False) as api_client:
        api_client.headers["Authorization"] = "Bearer studio-test-token"
        response = api_client.post(
            "/api/skills/text-segmentation/runs/run-1/resume",
            json={"human_input": "continue"},
        )

    assert response.status_code == 409
    body = response.json()
    assert body["error_code"] == "state.lease_conflict"
    assert body["http_status"] == 409
    assert body["details"] == payload


@pytest.mark.parametrize(
    ("error_code", "payload", "expected_status"),
    [
        ("state.invalid_checkpoint", {"run_id": "run-1", "detail": "Checkpoint is invalid"}, 422),
        ("state.lease_conflict", {"run_id": "run-1", "active_owner": "worker-a"}, 409),
        ("state.lease_fenced", {"run_id": "run-1", "action": "snapshot"}, 409),
        ("state.not_found", {"run_id": "run-1", "detail": "Snapshot not found"}, 404),
        ("state.release_failed", {"run_id": "run-1", "detail": "unlink failed"}, 409),
    ],
)
def test_d10_resume_api_preserves_runtime_state_error_codes_without_checkpoint_wrapping(
    monkeypatch: pytest.MonkeyPatch,
    error_code: str,
    payload: dict[str, Any],
    expected_status: int,
) -> None:
    import app.core.adapters.transport_factory as transport_factory
    from app.core.adapters.http_transport import StudioAdapterError
    from app.main import create_app

    class FakeAdapter:
        def resume(self, _payload: dict[str, Any]) -> dict[str, Any]:
            raise StudioAdapterError(error_code, payload)

    monkeypatch.setattr(transport_factory, "build_engine_adapter", lambda: FakeAdapter())

    with TestClient(create_app(), raise_server_exceptions=False) as api_client:
        api_client.headers["Authorization"] = "Bearer studio-test-token"
        response = api_client.post(
            "/api/skills/text-segmentation/runs/run-1/resume",
            json={"human_input": "continue"},
        )

    assert response.status_code == expected_status
    body = response.json()
    assert body["error_code"] == error_code
    assert body["http_status"] == expected_status
    assert body["details"] == payload
    assert body["error_code"] != "RESUME_CHECKPOINT_NOT_FOUND"


def test_run_endpoint_spawns_worker_and_ws_streams_events(
    client: TestClient,
    studio_roots: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _skills_dir, workspaces_dir = studio_roots
    monkeypatch.setattr(run_manager, "process_factory", InlineProcess)
    monkeypatch.setattr(run_manager, "queue_factory", queue.Queue)
    monkeypatch.setattr(run_manager, "worker", fake_run_worker)
    _record_predict_pass("text-segmentation")

    response = client.post(
        "/api/skills/text-segmentation/runs",
        json={"input_data": {"input_text": "hello"}},
    )

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "running"
    run_id = body["run_id"]

    with client.websocket_connect(f"/ws/runs/{run_id}") as websocket:
        stream_events = [websocket.receive_json() for _ in range(6)]
    event_types = [event["event_type"] for event in stream_events]
    assert event_types == [
        "run_started",
        "phase_start",
        "llm_call",
        "phase_end",
        "finish_task",
        "run_ended",
    ]
    assert [event["schema_version"] for event in stream_events] == ["studio.event.v1"] * 6
    assert [event["run_id"] for event in stream_events] == [run_id] * 6
    assert [event["seq"] for event in stream_events] == [1, 2, 3, 4, 5, 6]
    assert stream_events[0]["payload"]["event_type"] == "run_started"

    with client.websocket_connect(f"/ws/runs/{run_id}?cursor={stream_events[1]['cursor']}") as websocket:
        resumed_events = [websocket.receive_json() for _ in range(4)]
    assert [event["seq"] for event in resumed_events] == [3, 4, 5, 6]

    detail: dict[str, Any] = {}
    for _ in range(20):
        detail = client.get(f"/api/skills/text-segmentation/runs/{run_id}").json()
        if detail.get("metadata", {}).get("status") == "success":
            break
        time.sleep(0.05)

    assert detail["metadata"]["status"] == "success"
    assert [event["event_type"] for event in detail["events"]] == event_types
    assert [event["seq"] for event in detail["events"]] == [1, 2, 3, 4, 5, 6]
    assert detail["events"][1]["payload"]["phase_name"] == "setup"
    run_dir = _skills_dir / "text-segmentation" / ".workspace" / "runs" / run_id
    assert (run_dir / "final_state.json").exists()
    assert (run_dir / "trace.jsonl").exists()
    assert (run_dir / "metrics.json").exists()
    assert (run_dir / "artifacts").is_dir()
    assert (run_dir / "checkpoints.db").exists()
    assert (run_dir.parent / "latest" / "run_metadata.json").exists()


def test_successful_run_triggers_auto_commit(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commits: list[tuple[Path, str]] = []
    client.post(
        "/api/skills",
        json={"skill_id": "commit-skill", "files": _agent_skill_files("commit-skill")},
    )
    monkeypatch.setattr(run_manager, "process_factory", InlineProcess)
    monkeypatch.setattr(run_manager, "queue_factory", queue.Queue)
    monkeypatch.setattr(run_manager, "worker", fake_run_worker)
    monkeypatch.setattr(
        run_manager,
        "git_service",
        FakeGitService(commits),
    )
    _record_predict_pass("commit-skill")

    response = client.post("/api/skills/commit-skill/runs", json={"input_data": {"topic": "ok"}})

    assert response.status_code == 202
    run_id = response.json()["run_id"]
    for _ in range(20):
        detail = client.get(f"/api/skills/commit-skill/runs/{run_id}").json()
        if detail.get("metadata", {}).get("status") == "success":
            break
        time.sleep(0.05)
    assert commits == [(config.DEFAULT_SKILLS_ROOT / "commit-skill", run_id)]


def test_failed_run_does_not_auto_commit(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commits: list[tuple[Path, str]] = []
    client.post(
        "/api/skills",
        json={
            "skill_id": "failed-commit-skill",
            "files": _agent_skill_files("failed-commit-skill"),
        },
    )
    monkeypatch.setattr(run_manager, "process_factory", InlineProcess)
    monkeypatch.setattr(run_manager, "queue_factory", queue.Queue)
    monkeypatch.setattr(run_manager, "worker", fake_failed_run_worker)
    monkeypatch.setattr(run_manager, "git_service", FakeGitService(commits))
    _record_predict_pass("failed-commit-skill")

    response = client.post(
        "/api/skills/failed-commit-skill/runs",
        json={"input_data": {"topic": "fail"}},
    )

    assert response.status_code == 202
    run_id = response.json()["run_id"]
    for _ in range(20):
        detail = client.get(f"/api/skills/failed-commit-skill/runs/{run_id}").json()
        if detail.get("metadata", {}).get("status") == "failed":
            break
        time.sleep(0.05)
    assert commits == []


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


def test_delete_run_rejects_path_traversal(
    client: TestClient,
    studio_roots: tuple[Path, Path],
) -> None:
    _skills_dir, workspaces_dir = studio_roots
    safe_dir = _write_run_record(
        workspaces_dir,
        "text-segmentation",
        "safe-run",
        started_at=datetime.now(UTC),
        input_data={"chapter": "001"},
    )
    runs_dir = safe_dir.parent

    response = client.delete("/api/skills/text-segmentation/runs/%2E%2E")

    assert response.status_code == 400
    assert runs_dir.exists()
    assert safe_dir.exists()


def test_batch_run_starts_runs_from_test_inputs(
    client: TestClient,
    studio_roots: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    skills_dir, _workspaces_dir = studio_roots
    inputs_dir = skills_dir / "text-segmentation" / ".workspace" / "import_files"
    inputs_dir.mkdir(parents=True)
    for index in range(3):
        (inputs_dir / f"case-{index}.json").write_text(
            json.dumps({"input_text": f"hello {index}"}),
            encoding="utf-8",
        )
    monkeypatch.setattr(run_manager, "process_factory", InlineProcess)
    monkeypatch.setattr(run_manager, "queue_factory", queue.Queue)
    monkeypatch.setattr(run_manager, "worker", fake_run_worker)
    _record_predict_pass("text-segmentation")

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
    _write_result_snapshot(
        workspaces_dir,
        "text-segmentation",
        "golden-run",
        [
            {"phase_name": "setup", "outputs": {"answer": "hello world", "score": 10, "ok": True}},
        ],
    )
    _write_result_snapshot(
        workspaces_dir,
        "text-segmentation",
        "current-run",
        [
            {"phase_name": "setup", "outputs": {"answer": "hello studio", "score": 8, "ok": False}},
        ],
    )

    promote_response = client.post(
        "/api/skills/text-segmentation/golden",
        json={"run_id": "golden-run", "lock": False},
        headers=FALLBACK_HEADERS,
    )

    assert promote_response.status_code == 200
    assert promote_response.json()["id"] == "golden-run"
    assert promote_response.json()["source_run_id"] == "golden-run"
    assert promote_response.json()["source_run_results_ref"] == "text-segmentation/runs/golden-run/result.json"
    assert promote_response.json()["baseline_ref"] == ".workspace/golden/golden-run/baseline.json"
    golden_dir = _skills_dir / "text-segmentation" / ".workspace" / "golden" / "golden-run"
    assert (golden_dir / "baseline.json").exists()
    assert (golden_dir / "report.json").exists()
    assert (golden_dir / "cases" / "setup.json").exists()
    assert json.loads((golden_dir / "baseline.json").read_text(encoding="utf-8"))["locked"] is False
    assert not (golden_dir / "golden_metadata.json").exists()

    diff_response = client.get(
        "/api/skills/text-segmentation/runs/current-run/diff?against=golden-run",
    )

    assert diff_response.status_code == 200
    body = diff_response.json()
    assert body["baseline_id"] == "golden-run"
    assert body["source_run_id"] == "golden-run"
    assert body["run_results_ref"] == "text-segmentation/runs/current-run/result.json"
    assert body["total_score"] < 100
    assert "differences" not in body
    assert "node_results" not in body
    answer_diff = next(
        item for item in body["node_groups"][0]["field_differences"] if item["field_path"] == "nodes.setup.answer"
    )
    assert answer_diff["type"] == "text"
    assert answer_diff["changed"] is True
    assert answer_diff["score"] < 1


def test_set_golden_requires_explicit_browser_fallback_header(
    client: TestClient,
    studio_roots: tuple[Path, Path],
) -> None:
    skills_dir, workspaces_dir = studio_roots
    _write_final_state(
        workspaces_dir,
        "text-segmentation",
        "golden-run",
        {"answer": "must use native fs unless browser fallback is explicit"},
    )
    golden_dir = skills_dir / "text-segmentation" / ".workspace" / "golden" / "golden-run"

    response = client.post(
        "/api/skills/text-segmentation/golden",
        json={"run_id": "golden-run", "lock": False},
    )

    assert response.status_code == 409
    assert response.json()["error_code"] == "NATIVE_FS_REQUIRED"
    assert not golden_dir.exists()


def test_golden_plan_prepares_native_fs_payload_without_writing_baseline(
    client: TestClient,
    studio_roots: tuple[Path, Path],
) -> None:
    _skills_dir, workspaces_dir = studio_roots
    _write_result_snapshot(
        workspaces_dir,
        "text-segmentation",
        "plan-run",
        [{"phase_name": "setup", "outputs": {"answer": "native writer owns golden"}}],
    )
    golden_dir = _skills_dir / "text-segmentation" / ".workspace" / "golden" / "plan-run"

    response = client.post(
        "/api/skills/text-segmentation/golden/plan",
        json={"run_id": "plan-run", "lock": True},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["baseline"]["id"] == "plan-run"
    assert body["baseline"]["source_run_id"] == "plan-run"
    assert body["baseline"]["source_run_results_ref"] == "text-segmentation/runs/plan-run/result.json"
    assert body["baseline"]["baseline_ref"] == ".workspace/golden/plan-run/baseline.json"
    assert body["baseline"]["locked"] is True
    files = {item["path"]: json.loads(item["content"]) for item in body["files"]}
    assert files[".workspace/golden/plan-run/baseline.json"]["locked"] is True
    assert files[".workspace/golden/plan-run/baseline.json"]["cases"][0]["node_id"] == "setup"
    assert files[".workspace/golden/plan-run/report.json"]["case_count"] == 1
    assert files[".workspace/golden/plan-run/cases/setup.json"]["expected_output"] == {
        "answer": "native writer owns golden"
    }
    assert "result_path" not in body
    assert "result_content" not in body
    assert "metadata_path" not in body
    assert "metadata_content" not in body
    assert not golden_dir.exists()


def test_compare_endpoint_returns_per_node_golden_diff(
    client: TestClient,
    studio_roots: tuple[Path, Path],
) -> None:
    _skills_dir, workspaces_dir = studio_roots
    _write_result_snapshot(
        workspaces_dir,
        "text-segmentation",
        "golden-node-run",
        [
            {"phase_name": "setup", "outputs": {"answer": "hello world", "ok": True}},
            {"phase_name": "review", "outputs": {"score": 10}},
        ],
    )
    _write_result_snapshot(
        workspaces_dir,
        "text-segmentation",
        "current-node-run",
        [
            {"phase_name": "setup", "outputs": {"answer": "hello studio", "ok": True}},
            {"phase_name": "review", "outputs": {"score": 10}},
        ],
    )

    promote_response = client.post(
        "/api/skills/text-segmentation/golden",
        json={"run_id": "golden-node-run", "lock": False},
        headers=FALLBACK_HEADERS,
    )
    assert promote_response.status_code == 200

    compare_response = client.get("/api/skills/text-segmentation/runs/current-node-run/compare")

    assert compare_response.status_code == 200
    body = compare_response.json()
    assert [node["node_id"] for node in body["node_groups"]] == ["setup", "review"]
    assert body["node_groups"][0]["status"] == "fail"
    assert body["node_groups"][0]["field_differences"][0]["field_path"] == "nodes.setup.answer"
    assert body["node_groups"][1]["status"] == "pass"
    assert body["node_groups"][1]["field_differences"] == []


def test_compare_missing_golden_returns_404(
    client: TestClient,
    studio_roots: tuple[Path, Path],
) -> None:
    _skills_dir, workspaces_dir = studio_roots
    _write_final_state(workspaces_dir, "text-segmentation", "current-run", {"answer": "hello"})

    response = client.get("/api/skills/text-segmentation/runs/current-run/diff")

    assert response.status_code == 404
    assert response.json()["error_code"] == "golden.baseline_not_found"


def test_set_golden_with_node_id_writes_only_that_node(
    client: TestClient,
    studio_roots: tuple[Path, Path],
) -> None:
    """POST golden with node_id promotes one agent node, not the whole run (GOLDEN_EVAL-1)."""
    skills_dir, workspaces_dir = studio_roots
    _write_result_snapshot(
        workspaces_dir,
        "text-segmentation",
        "node-set-run",
        [
            {"phase_name": "setup", "outputs": {"answer": "hello world"}},
            {"phase_name": "review", "outputs": {"score": 10}},
        ],
    )

    response = client.post(
        "/api/skills/text-segmentation/golden",
        json={"run_id": "node-set-run", "lock": False, "node_id": "review"},
        headers=FALLBACK_HEADERS,
    )

    assert response.status_code == 200
    golden_dir = skills_dir / "text-segmentation" / ".workspace" / "golden" / "node-set-run"
    assert (golden_dir / "cases" / "review.json").exists()
    assert not (golden_dir / "cases" / "setup.json").exists()
    cases = response.json()["cases"]
    assert [case["node_id"] for case in cases] == ["review"]


def test_set_golden_second_node_merges_without_clobbering_first(
    client: TestClient,
    studio_roots: tuple[Path, Path],
) -> None:
    """A node-scoped write must not auto-overwrite a sibling node's golden (F6)."""
    skills_dir, workspaces_dir = studio_roots
    _write_result_snapshot(
        workspaces_dir,
        "text-segmentation",
        "node-merge-run",
        [
            {"phase_name": "setup", "outputs": {"answer": "hello world"}},
            {"phase_name": "review", "outputs": {"score": 10}},
        ],
    )

    first = client.post(
        "/api/skills/text-segmentation/golden",
        json={"run_id": "node-merge-run", "lock": False, "node_id": "setup"},
        headers=FALLBACK_HEADERS,
    )
    assert first.status_code == 200
    second = client.post(
        "/api/skills/text-segmentation/golden",
        json={"run_id": "node-merge-run", "lock": False, "node_id": "review"},
        headers=FALLBACK_HEADERS,
    )
    assert second.status_code == 200

    golden_dir = skills_dir / "text-segmentation" / ".workspace" / "golden" / "node-merge-run"
    assert (golden_dir / "cases" / "setup.json").exists()
    assert (golden_dir / "cases" / "review.json").exists()
    cases = client.get("/api/skills/text-segmentation/golden").json()[0]["cases"]
    assert sorted(case["node_id"] for case in cases) == ["review", "setup"]


def test_list_golden_projects_cases(
    client: TestClient,
    studio_roots: tuple[Path, Path],
) -> None:
    """GET golden projects per-node cases — the three-state badge's source of truth."""
    _skills_dir, workspaces_dir = studio_roots
    _write_result_snapshot(
        workspaces_dir,
        "text-segmentation",
        "list-cases-run",
        [
            {"phase_name": "setup", "outputs": {"answer": "hello world"}},
            {"phase_name": "review", "outputs": {"score": 10}},
        ],
    )
    promote = client.post(
        "/api/skills/text-segmentation/golden",
        json={"run_id": "list-cases-run", "lock": False},
        headers=FALLBACK_HEADERS,
    )
    assert promote.status_code == 200

    listed = client.get("/api/skills/text-segmentation/golden")

    assert listed.status_code == 200
    body = listed.json()
    assert len(body) == 1
    assert sorted(case["node_id"] for case in body[0]["cases"]) == ["review", "setup"]


def test_set_golden_node_scoped_still_runs_predict_guard(
    client: TestClient,
    studio_roots: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """F6 guard holds for node-scoped writes: the predict-trace 409 is not bypassed.

    The guard verdict is exercised by its own unit tests; here we assert the
    node-scoped promote path still routes the snapshot through the guard, so a
    detected predict trace surfaces as 409 instead of being silently promoted.
    """
    _skills_dir, workspaces_dir = studio_roots
    _write_result_snapshot(
        workspaces_dir,
        "text-segmentation",
        "predict-node-run",
        [{"phase_name": "setup", "outputs": {"answer": "fake"}}],
    )

    from app.services import golden_diff

    def _reject_predict(trace_payload: dict[str, Any], *, skill_id: str, run_id: str) -> None:
        del trace_payload, skill_id, run_id
        from app.core.exceptions import error_response, raise_error_response

        raise_error_response(
            error_response(
                error_code="PREDICT_TRACE_CANNOT_BE_GOLDEN",
                http_status=409,
                message="Predict traces cannot be saved as Golden baselines",
                details={},
                retry_strategy="not_retryable",
            )
        )

    monkeypatch.setattr(golden_diff, "assert_trace_can_be_promoted_to_golden", _reject_predict)

    response = client.post(
        "/api/skills/text-segmentation/golden",
        json={"run_id": "predict-node-run", "lock": False, "node_id": "setup"},
        headers=FALLBACK_HEADERS,
    )

    assert response.status_code == 409
    assert response.json()["error_code"] == "PREDICT_TRACE_CANNOT_BE_GOLDEN"


def test_run_spawn_failure_maps_to_500(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(run_manager, "process_factory", FailingProcess)
    monkeypatch.setattr(run_manager, "queue_factory", queue.Queue)
    _record_predict_pass("text-segmentation")

    response = client.post(
        "/api/skills/text-segmentation/runs",
        json={"input_data": {"input_text": "hello"}},
    )

    assert response.status_code == 500
    assert response.json()["error_code"] == "RUN_SPAWN_FAILED"


def test_run_without_prior_predict_returns_run_requires_predict(
    client: TestClient,
    studio_roots: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # No predict-pass on record: the server-side gate must block the run-spawn
    # path before any worker is started, for any caller (not just the UI).
    del studio_roots
    monkeypatch.setattr(run_manager, "process_factory", InlineProcess)
    monkeypatch.setattr(run_manager, "queue_factory", queue.Queue)
    monkeypatch.setattr(run_manager, "worker", fake_run_worker)

    response = client.post(
        "/api/skills/text-segmentation/runs",
        json={"input_data": {"input_text": "hello"}},
    )

    assert response.status_code == 409
    body = response.json()
    assert body["error_code"] == "RUN_REQUIRES_PREDICT"
    assert body["details"]["skill_id"] == "text-segmentation"


def test_run_after_passing_predict_is_allowed(
    client: TestClient,
    studio_roots: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A passing predict on record satisfies the gate and lets the run spawn.
    del studio_roots
    monkeypatch.setattr(run_manager, "process_factory", InlineProcess)
    monkeypatch.setattr(run_manager, "queue_factory", queue.Queue)
    monkeypatch.setattr(run_manager, "worker", fake_run_worker)
    _record_predict_pass("text-segmentation")

    response = client.post(
        "/api/skills/text-segmentation/runs",
        json={"input_data": {"input_text": "hello"}},
    )

    assert response.status_code == 202
    assert response.json()["status"] == "running"


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
        websocket.close()
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


def test_delete_golden_baseline_removes_persisted_baseline(
    client: TestClient,
    studio_roots: tuple[Path, Path],
) -> None:
    _skills_dir, workspaces_dir = studio_roots
    _write_result_snapshot(
        workspaces_dir,
        "text-segmentation",
        "delete-golden-run",
        [{"phase_name": "setup", "outputs": {"answer": "remove me"}}],
    )

    promote_response = client.post(
        "/api/skills/text-segmentation/golden",
        json={"run_id": "delete-golden-run", "lock": False},
        headers=FALLBACK_HEADERS,
    )
    assert promote_response.status_code == 200

    delete_response = client.delete(
        "/api/skills/text-segmentation/golden/delete-golden-run",
        headers=FALLBACK_HEADERS,
    )

    assert delete_response.status_code == 204
    assert client.get("/api/skills/text-segmentation/golden").json() == []


def test_delete_golden_requires_explicit_browser_fallback_header(
    client: TestClient,
    studio_roots: tuple[Path, Path],
) -> None:
    skills_dir, _workspaces_dir = studio_roots
    golden_dir = skills_dir / "text-segmentation" / ".workspace" / "golden" / "delete-golden-run"
    golden_dir.mkdir(parents=True, exist_ok=True)
    (golden_dir / "baseline.json").write_text(
        json.dumps(
            {
                "baseline_id": "delete-golden-run",
                "source_run_id": "source-run",
                "source_run_results_ref": "text-segmentation/runs/source-run/result.json",
                "cases": [],
            }
        ),
        encoding="utf-8",
    )

    response = client.delete("/api/skills/text-segmentation/golden/delete-golden-run")

    assert response.status_code == 409
    assert response.json()["error_code"] == "NATIVE_FS_REQUIRED"
    assert golden_dir.exists()


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
    for origin in (
        "http://localhost:5173",
        "http://127.0.0.1:5174",
        "http://localhost:3000",
    ):
        response = client.options(
            "/api/skills",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "GET",
            },
        )
        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == origin


def test_cors_allows_packaged_tauri_webview_origins(client: TestClient) -> None:
    # The packaged desktop .app serves its frontend from the Tauri custom
    # protocol origin (tauri://localhost on macOS/Linux, http://tauri.localhost
    # on Windows). Without these in the allow-list the bundled UI cannot make any
    # HTTP API call (it can only open the WebSocket, which is not CORS-gated),
    # which surfaces as a permanent "Could not load skills".
    for origin in ("tauri://localhost", "http://tauri.localhost"):
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
    run_dir_raw: str,
    inputs: dict[str, Any],
    process_queue: queue.Queue[dict[str, Any]],
    art_ref: dict[str, Any],
    roles_path_override: str | None = None,
    runtime_config: dict[str, Any] | None = None,
) -> None:
    del art_ref, inputs, roles_path_override, runtime_config
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
    trace_jsonl = "\n".join(event.model_dump_json() for event in events) + "\n"
    final_state = {"ok": True}
    (run_dir / "trace.jsonl").write_text(trace_jsonl, encoding="utf-8")
    (run_dir / "final_state.json").write_text(json.dumps(final_state), encoding="utf-8")
    _write_run_artifact_store(run_dir, final_state=final_state, trace_jsonl=trace_jsonl)
    (run_dir / "metrics.json").write_text(json.dumps({"status": "success"}), encoding="utf-8")
    (run_dir / "checkpoints.db").touch()
    for event in events:
        process_queue.put({"type": "event", "event": event.model_dump(mode="json")})
    process_queue.put({"type": "status", "status": "success", "metrics": {}})


def fake_failed_run_worker(
    skill_id: str,
    run_dir_raw: str,
    inputs: dict[str, Any],
    process_queue: queue.Queue[dict[str, Any]],
    art_ref: dict[str, Any],
    roles_path_override: str | None = None,
    runtime_config: dict[str, Any] | None = None,
) -> None:
    del skill_id, art_ref, inputs, roles_path_override, runtime_config
    run_dir = Path(run_dir_raw)
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "final_state.json").write_text(json.dumps({}), encoding="utf-8")
    (run_dir / "metrics.json").write_text(json.dumps({"status": "failed"}), encoding="utf-8")
    process_queue.put({"type": "status", "status": "failed", "metrics": {}})


class FakeGitService:
    def __init__(self, commits: list[tuple[Path, str]]) -> None:
        self._commits = commits

    def auto_commit_run(self, skill_dir: Path, run_id: str) -> object:
        self._commits.append((skill_dir, run_id))
        # Non-None mirrors GitLocalService returning a commit result for a real
        # git repo, so the run is reported committed (not the no_git boundary).
        return object()


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
    return _agent_skill_files(skill_id)["GRAPH.md"]


def _agent_skill_files(skill_id: str) -> dict[str, str]:
    return {
        "GRAPH.md": f"""---
schema_version: "v0.3.0"
name: {skill_id}
description: Draft structured ideas
io:
  inputs:
    type: object
    properties:
      topic:
        type: string
      input_text:
        type: string
    additionalProperties: true
  outputs:
    type: object
    properties:
      prepared:
        type: boolean
    additionalProperties: true
phases:
  - setup
---
<phase depends_on="input" output>setup</phase>
""",
        "phases/setup/LOGIC.md": """---
io:
  inputs:
    type: object
    properties:
      topic:
        type: string
      input_text:
        type: string
  outputs:
    type: object
    properties:
      prepared:
        type: boolean
---
<action>prepare</action>
""",
        "phases/setup/actions/prepare.py": """def prepare(inputs):
    return {"prepared": True}
""",
    }

def _write_final_state(
    workspaces_dir: Path,
    skill_id: str,
    run_id: str,
    payload: dict[str, Any],
) -> Path:
    del workspaces_dir
    run_dir = resolve_skill_dir(skill_id) / ".workspace" / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "final_state.json").write_text(json.dumps(payload), encoding="utf-8")
    return run_dir


def _write_result_state(
    workspaces_dir: Path,
    skill_id: str,
    run_id: str,
    payload: dict[str, Any],
) -> Path:
    del workspaces_dir
    run_dir = resolve_skill_dir(skill_id) / ".workspace" / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "result.json").write_text(json.dumps(payload), encoding="utf-8")
    return run_dir


def _write_result_snapshot(
    workspaces_dir: Path,
    skill_id: str,
    run_id: str,
    phases: list[dict[str, Any]],
) -> Path:
    del workspaces_dir
    run_dir = resolve_skill_dir(skill_id) / ".workspace" / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    node_outputs: dict[str, Any] = {}
    for index, phase in enumerate(phases):
        node_id = phase.get("phase_name") or phase.get("node_id") or f"node_{index}"
        node_outputs[str(node_id)] = phase.get("outputs", {})
    _write_run_result_snapshot_store(
        run_dir,
        skill_id=skill_id,
        run_id=run_id,
        node_outputs=node_outputs,
    )
    return run_dir


def _write_run_result_snapshot_store(
    run_dir: Path,
    *,
    skill_id: str,
    run_id: str,
    node_outputs: dict[str, Any],
) -> None:
    from app.core.adapters.run_artifact_store_local import LocalRunArtifactStore

    store = LocalRunArtifactStore(root=run_dir.parent.parent)
    object_payloads = {
        f"nodes/{node_id}/outputs.json": json.dumps(outputs).encode("utf-8")
        for node_id, outputs in node_outputs.items()
    }
    snapshot = RunResultSnapshot(
        run_results_ref=RunResultsRef(
            run_id=run_id,
            uri=f"{skill_id}/runs/{run_id}/result.json",
            content_hash="sha256:" + ("0" * 64),
        ),
        node_results=[
            NodeRunResult(
                agent_node_id=node_id,
                status="success",
                outputs_ref=f"{skill_id}/runs/{run_id}/nodes/{node_id}/outputs.json",
                trace_refs=[f"{skill_id}/runs/{run_id}/trace/{node_id}.jsonl"],
            )
            for node_id in node_outputs
        ],
        status="success",
        outputs_ref=f"{skill_id}/runs/{run_id}/outputs.json",
        trace_refs=[f"{skill_id}/runs/{run_id}/trace.jsonl"],
    )
    object_payloads["result.json"] = snapshot.model_dump_json().encode("utf-8")
    store.begin_run(run_id, metadata={"artifact_id": skill_id})
    store.put_batch(run_id, object_payloads)
    store.seal_run(run_id)


def _write_run_record(
    workspaces_dir: Path,
    skill_id: str,
    run_id: str,
    *,
    started_at: datetime,
    input_data: dict[str, Any],
) -> Path:
    final_state = {"ok": True}
    run_dir = _write_final_state(workspaces_dir, skill_id, run_id, final_state)
    metadata = RunMetadata(run_id=run_id, status="success", started_at=started_at)
    (run_dir / "run_metadata.json").write_text(metadata.model_dump_json(), encoding="utf-8")
    (run_dir / "input_data.json").write_text(json.dumps(input_data), encoding="utf-8")
    _write_run_artifact_store(run_dir, final_state=final_state, trace_jsonl="", input_data=input_data)
    return run_dir


def _write_run_artifact_store(
    run_dir: Path,
    *,
    final_state: dict[str, Any],
    trace_jsonl: str,
    input_data: dict[str, Any] | None = None,
) -> None:
    from app.core.adapters.run_artifact_store_local import LocalRunArtifactStore

    store = LocalRunArtifactStore(root=run_dir.parent.parent)
    node_outputs = {"setup": final_state}
    snapshot = RunResultSnapshot(
        run_results_ref=RunResultsRef(
            run_id=run_dir.name,
            uri=f"{run_dir.parent.parent.parent.name}/runs/{run_dir.name}/result.json",
            content_hash="sha256:" + ("0" * 64),
        ),
        node_results=[
            NodeRunResult(
                agent_node_id=node_id,
                status="success",
                outputs_ref=f"{run_dir.parent.parent.parent.name}/runs/{run_dir.name}/nodes/{node_id}/outputs.json",
                trace_refs=[f"{run_dir.parent.parent.parent.name}/runs/{run_dir.name}/trace.jsonl"],
            )
            for node_id in node_outputs
        ],
        status="success",
        outputs_ref=f"{run_dir.parent.parent.parent.name}/runs/{run_dir.name}/outputs.json",
        trace_refs=[f"{run_dir.parent.parent.parent.name}/runs/{run_dir.name}/trace.jsonl"],
    )
    store.put_batch(
        run_dir.name,
        {
            "result.json": snapshot.model_dump_json().encode("utf-8"),
            "nodes/setup/outputs.json": json.dumps(final_state).encode("utf-8"),
            "final_state.json": json.dumps(final_state).encode("utf-8"),
            "input_data.json": json.dumps(input_data or {}).encode("utf-8"),
            "trace.jsonl": trace_jsonl.encode("utf-8"),
        },
    )
    store.seal_run(run_dir.name)
