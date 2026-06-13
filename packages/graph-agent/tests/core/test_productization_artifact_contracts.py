from __future__ import annotations

import dataclasses
import importlib
import inspect
from typing import Any

import pytest


def _fields(cls: type[Any]) -> set[str]:
    if hasattr(cls, "model_fields"):
        return set(cls.model_fields)
    if dataclasses.is_dataclass(cls):
        return {field.name for field in dataclasses.fields(cls)}
    try:
        return {
            name
            for name in inspect.signature(cls).parameters
            if name != "self"
        }
    except (TypeError, ValueError):
        return set(getattr(cls, "__annotations__", {}))


def _artifact_ref() -> Any:
    artifacts = importlib.import_module("graph_agent.core.artifacts")
    ArtifactRef = artifacts.ArtifactRef
    return ArtifactRef(
        artifact_id="artifact-runner-demo",
        content_hash="sha256:6f2c1b0a",
        store="ephemeral",
        version=None,
        manifest_ref="object://manifest.json",
        source_map_ref="object://source-map.json",
    )


def test_artifact_ref_and_compiled_manifest_define_frozen_identity_contract() -> None:
    artifacts = importlib.import_module("graph_agent.core.artifacts")

    ArtifactRef = artifacts.ArtifactRef
    CompiledArtifactManifest = artifacts.CompiledArtifactManifest

    assert {
        "artifact_id",
        "content_hash",
        "store",
        "version",
        "manifest_ref",
        "source_map_ref",
    } <= _fields(ArtifactRef)
    assert {
        "artifact_ref",
        "execution_fingerprint",
        "source_map_ref",
        "diagnostics",
    } <= _fields(CompiledArtifactManifest)

    ref = _artifact_ref()
    assert ref.content_hash == "sha256:6f2c1b0a"
    assert ref.store == "ephemeral"
    assert ref.manifest_ref == "object://manifest.json"
    assert ref.source_map_ref == "object://source-map.json"

    with pytest.raises((TypeError, ValueError)):
        ArtifactRef(
            artifact_id="bad",
            content_hash="sha256:bad",
            store="source",
            version=None,
            manifest_ref="object://manifest.json",
            source_map_ref="object://source-map.json",
        )

    manifest = CompiledArtifactManifest(
        artifact_ref=ref,
        execution_fingerprint="sha256:execution-only",
        source_map_ref="object://source-map.json",
        diagnostics=[],
    )
    assert manifest.artifact_ref is ref
    assert manifest.execution_fingerprint == "sha256:execution-only"
    assert manifest.source_map_ref == "object://source-map.json"


@pytest.mark.parametrize(
    ("class_name", "kwargs"),
    [
        (
            "RunArtifactRequest",
            {
                "artifact_ref": None,
                "inputs": {"topic": "red"},
                "execution_context": {"workspace_id": "local"},
                "idempotency_key": "idem-run-1",
            },
        ),
        (
            "PredictArtifactRequest",
            {
                "artifact_ref": None,
                "inputs": {"topic": "red"},
                "execution_context": {"workspace_id": "local"},
                "idempotency_key": "idem-predict-1",
            },
        ),
        (
            "ResumeRequest",
            {
                "run_id": "run-1",
                "payload": {"human_response": {"answer": "continue"}},
                "idempotency_key": "idem-resume-1",
            },
        ),
    ],
)
def test_runtime_requests_require_idempotency_key_and_never_accept_skill_path(
    class_name: str,
    kwargs: dict[str, Any],
) -> None:
    adapters = importlib.import_module("graph_agent.core.adapter_contracts")
    request_cls = getattr(adapters, class_name)
    request_fields = _fields(request_cls)

    assert "idempotency_key" in request_fields
    assert "skill_path" not in request_fields

    valid_kwargs = dict(kwargs)
    if "artifact_ref" in valid_kwargs:
        valid_kwargs["artifact_ref"] = _artifact_ref()
    request = request_cls(**valid_kwargs)
    assert request.idempotency_key == kwargs["idempotency_key"]

    missing_idempotency_key = dict(valid_kwargs)
    missing_idempotency_key.pop("idempotency_key")
    with pytest.raises((TypeError, ValueError)):
        request_cls(**missing_idempotency_key)


def test_run_session_exposes_event_result_and_status_refs_without_source_path() -> None:
    adapters = importlib.import_module("graph_agent.core.adapter_contracts")
    RunSession = adapters.RunSession

    assert {
        "run_id",
        "event_stream_ref",
        "result_ref",
        "status_ref",
    } <= _fields(RunSession)
    assert "skill_path" not in _fields(RunSession)

    session = RunSession(
        run_id="run-1",
        event_stream_ref="stream://run-1",
        result_ref=None,
        status_ref="state://run-1/status",
    )

    assert session.run_id == "run-1"
    assert session.event_stream_ref == "stream://run-1"
    assert session.status_ref == "state://run-1/status"


def test_runtime_requests_and_session_reject_skill_path() -> None:
    adapters = importlib.import_module("graph_agent.core.adapter_contracts")
    RunArtifactRequest = adapters.RunArtifactRequest
    PredictArtifactRequest = adapters.PredictArtifactRequest
    ResumeRequest = adapters.ResumeRequest
    RunSession = adapters.RunSession

    ref = _artifact_ref()

    # 1. Verify RunArtifactRequest rejects skill_path extra field
    with pytest.raises((TypeError, ValueError)):
        RunArtifactRequest(
            artifact_ref=ref,
            inputs={"topic": "red"},
            execution_context={"workspace_id": "local"},
            idempotency_key="idem-1",
            skill_path="bad",
        )

    # 2. Verify PredictArtifactRequest rejects skill_path extra field
    with pytest.raises((TypeError, ValueError)):
        PredictArtifactRequest(
            artifact_ref=ref,
            inputs={"topic": "red"},
            execution_context={"workspace_id": "local"},
            idempotency_key="idem-2",
            skill_path="bad",
        )

    # 3. Verify ResumeRequest rejects skill_path extra field
    with pytest.raises((TypeError, ValueError)):
        ResumeRequest(
            run_id="run-1",
            payload={"human_response": {"answer": "continue"}},
            idempotency_key="idem-3",
            skill_path="bad",
        )

    # 4. Verify RunSession rejects skill_path extra field
    with pytest.raises((TypeError, ValueError)):
        RunSession(
            run_id="run-1",
            event_stream_ref="stream://run-1",
            result_ref=None,
            status_ref="state://run-1/status",
            skill_path="bad",
        )

