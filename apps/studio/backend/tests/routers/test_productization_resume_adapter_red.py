from __future__ import annotations

import io
import zipfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from fastapi.testclient import TestClient


def test_resume_endpoint_is_no_longer_not_implemented(client: TestClient) -> None:
    response = client.post(
        "/api/skills/text-segmentation/runs/run-123/resume",
        json={"human_input": "continue from checkpoint"},
    )

    assert response.status_code != 501


def test_resume_endpoint_delegates_to_configured_engine_adapter_resume(
    client: TestClient,
    monkeypatch,
) -> None:
    import app.core.adapters.transport_factory as transport_factory

    calls: list[dict[str, Any]] = []

    class FakeAdapter:
        def resume(self, payload: dict[str, Any]) -> dict[str, Any]:
            calls.append(payload)
            return {
                "run_id": payload["run_id"],
                "status": "success",
                "started_at": "2026-06-17T00:00:00Z",
                "input_summary": "resumed",
                "metrics": {
                    "input_tokens": 1,
                    "output_tokens": 2,
                    "total_tokens": 3,
                },
            }

    monkeypatch.setattr(transport_factory, "build_engine_adapter", lambda: FakeAdapter())

    response = client.post(
        "/api/skills/text-segmentation/runs/run-123/resume",
        json={
            "human_input": "continue from checkpoint",
            "context_overrides": {"draft": "manual"},
        },
    )

    assert response.status_code == 200
    assert calls == [
        {
            "skill_id": "text-segmentation",
            "run_id": "run-123",
            "context_overrides": {"draft": "manual"},
            "human_input": "continue from checkpoint",
        }
    ]
    assert response.json()["metrics"] == {
        "input_tokens": 1,
        "output_tokens": 2,
        "total_tokens": 3,
        "cost_estimate": None,
    }


def test_resume_endpoint_forwards_checkpoint_selector_and_structured_human_response(
    client: TestClient,
    monkeypatch,
) -> None:
    import app.core.adapters.transport_factory as transport_factory

    calls: list[dict[str, Any]] = []

    class FakeAdapter:
        def resume(self, payload: dict[str, Any]) -> dict[str, Any]:
            calls.append(payload)
            return {
                "run_id": payload["run_id"],
                "status": "success",
                "started_at": "2026-06-17T00:00:00Z",
                "input_summary": "resumed",
                "metrics": {},
            }

    monkeypatch.setattr(transport_factory, "build_engine_adapter", lambda: FakeAdapter())

    response = client.post(
        "/api/skills/text-segmentation/runs/run-123/resume",
        json={
            "checkpoint_id": "checkpoint-review",
            "checkpoint_ns": "agent:review",
            "resume_from_node_id": "review",
            "resume_to_node_id": "final",
            "context_overrides": {"draft": "manual"},
            "human_response": {"content": "approved", "tool_call_id": "tool-1"},
        },
    )

    assert response.status_code == 200
    assert calls == [
        {
            "skill_id": "text-segmentation",
            "run_id": "run-123",
            "checkpoint_id": "checkpoint-review",
            "checkpoint_ns": "agent:review",
            "resume_from_node_id": "review",
            "resume_to_node_id": "final",
            "context_overrides": {"draft": "manual"},
            "human_input": None,
            "human_response": {"content": "approved", "tool_call_id": "tool-1"},
        }
    ]


def test_resume_endpoint_maps_state_release_failed_to_retryable_conflict(
    client: TestClient,
    monkeypatch,
) -> None:
    import app.core.adapters.transport_factory as transport_factory
    from app.core.adapters.http_transport import StudioAdapterError

    class FakeAdapter:
        def resume(self, _payload: dict[str, Any]) -> dict[str, Any]:
            raise StudioAdapterError(
                "state.release_failed",
                {"detail": "Lease release failed", "run_id": "run-123"},
            )

    monkeypatch.setattr(transport_factory, "build_engine_adapter", lambda: FakeAdapter())

    response = client.post(
        "/api/skills/text-segmentation/runs/run-123/resume",
        json={"human_input": "continue from checkpoint"},
    )

    assert response.status_code == 409
    body = response.json()
    assert body["error_code"] == "state.release_failed"
    assert body["retry_strategy"] == "backoff"


def test_resume_endpoint_accepts_real_engine_resume_wall_time_metrics(
    client: TestClient,
    monkeypatch,
) -> None:
    import graph_agent
    from app.core import config
    from app.core.adapters.runtime_state_store_local import LocalRuntimeStateStore

    storage_root = config.WORKSPACES_DIR / "default"
    run_id = "run-real-engine-metrics"
    artifact_ref = _store_artifact_zip(storage_root, artifact_id="text-segmentation", marker="snapshot")
    checkpointer_path = (
        storage_root
        / "skills"
        / "text-segmentation"
        / ".workspace"
        / "runs"
        / run_id
        / "checkpoints.db"
    )
    checkpointer_spec = f"sqlite:{checkpointer_path}"
    checkpointer_path.parent.mkdir(parents=True)
    checkpointer_path.write_bytes(b"")

    state_store = LocalRuntimeStateStore(root=storage_root)
    lease = state_store.acquire_lease(run_id=run_id, owner_id="test", ttl_ms=30_000)
    state_store.snapshot(
        run_id=run_id,
        state={
            "schema_version": "studio.runtime_state.v1",
            "run_id": run_id,
            "artifact_ref": artifact_ref,
            "checkpointer_spec": checkpointer_spec,
            "checkpoint_id": "checkpoint-1",
            "checkpoint_ns": "",
        },
        lease=lease,
    )
    state_store.release(run_id=run_id, lease=lease)

    monkeypatch.setattr(
        "graph_agent.core.checkpointer.resolve_checkpointer",
        lambda _spec: object(),
    )

    def fake_resume_skill(*_args: Any, **_kwargs: Any) -> SimpleNamespace:
        return SimpleNamespace(
            success=True,
            started_at=None,
            metrics=SimpleNamespace(model_dump=lambda mode="json": {"wall_time_sec": 0.125}),
        )

    monkeypatch.setattr(graph_agent, "resume_skill", fake_resume_skill)

    response = client.post(
        f"/api/skills/text-segmentation/runs/{run_id}/resume",
        json={"human_input": "continue from checkpoint"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["run_id"] == run_id
    assert body["status"] == "success"
    assert body["metrics"] == {
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "cost_estimate": None,
    }


def test_engine_resume_uses_snapshot_artifact_ref_instead_of_recompiling_current_skill(
    client: TestClient,
    monkeypatch,
) -> None:
    import graph_agent
    from app.core import config
    from app.core.adapters.engine import EngineAdapter
    from app.core.adapters.runtime_state_store_local import LocalRuntimeStateStore

    storage_root = config.WORKSPACES_DIR / "default"
    run_id = "run-snapshot-artifact"
    artifact_ref = _store_artifact_zip(storage_root, artifact_id="text-segmentation", marker="original-artifact")
    checkpointer_path = (
        storage_root
        / "skills"
        / "text-segmentation"
        / ".workspace"
        / "runs"
        / run_id
        / "checkpoints.db"
    )
    checkpointer_spec = f"sqlite:{checkpointer_path}"
    checkpointer_path.parent.mkdir(parents=True)
    checkpointer_path.write_bytes(b"")
    state_store = LocalRuntimeStateStore(root=storage_root)
    lease = state_store.acquire_lease(run_id=run_id, owner_id="test", ttl_ms=30_000)
    state_store.snapshot(
        run_id=run_id,
        state={
            "schema_version": "studio.runtime_state.v1",
            "run_id": run_id,
            "artifact_ref": artifact_ref,
            "checkpointer_spec": checkpointer_spec,
            "checkpoint_id": "checkpoint-1",
            "checkpoint_ns": "",
        },
        lease=lease,
    )
    state_store.release(run_id=run_id, lease=lease)

    monkeypatch.setattr(
        "graph_agent.core.checkpointer.resolve_checkpointer",
        lambda _spec: object(),
    )

    def fail_compile(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        raise AssertionError("resume must use the artifact_ref from RuntimeStateStore")

    monkeypatch.setattr(EngineAdapter, "compile", fail_compile)
    captured: dict[str, Path] = {}

    def fake_resume_skill(skill_path: str | Path, **kwargs: Any) -> SimpleNamespace:
        captured["skill_path"] = Path(skill_path)
        captured["workspace_dir"] = Path(kwargs["workspace_dir"])
        return SimpleNamespace(
            success=True,
            started_at=None,
            metrics=SimpleNamespace(model_dump=lambda mode="json": {}),
        )

    monkeypatch.setattr(graph_agent, "resume_skill", fake_resume_skill)

    response = client.post(
        f"/api/skills/text-segmentation/runs/{run_id}/resume",
        json={"human_input": "continue from checkpoint"},
    )

    assert response.status_code == 200
    resumed_graph = captured["skill_path"] / "GRAPH.md"
    assert "original-artifact" in resumed_graph.read_text(encoding="utf-8")
    assert captured["workspace_dir"] == storage_root / "skills" / "text-segmentation" / ".workspace"


def _store_artifact_zip(storage_root: Path, *, artifact_id: str, marker: str) -> dict[str, Any]:
    from app.core.adapters.product_store_local import LocalProductArtifactStore

    store = LocalProductArtifactStore(root=storage_root)
    artifact = store.put(_artifact_zip_bytes(marker), artifact_id=artifact_id, store="ephemeral")
    return {
        "artifact_id": artifact.artifact_id,
        "content_hash": artifact.content_hash,
        "store": artifact.store,
        "manifest_ref": artifact.manifest_ref,
        "source_map_ref": artifact.source_map_ref,
        "version": None,
    }


def _artifact_zip_bytes(marker: str) -> bytes:
    graph = f"""---
schema_version: "v0.3.0"
name: text-segmentation
description: {marker}
io:
  inputs:
    type: object
    properties: {{}}
  outputs:
    type: object
    properties: {{}}
phases: []
---
"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("GRAPH.md", graph)
    return buf.getvalue()
