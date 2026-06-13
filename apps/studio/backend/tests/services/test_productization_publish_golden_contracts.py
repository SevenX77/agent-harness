from __future__ import annotations

import importlib
from typing import Any

import pytest


def test_publish_request_contract_requires_artifact_ref_release_idempotency_and_atomic_stage() -> None:
    PublishArtifactRequest = _load_symbol(
        "app.services.publish_pipeline",
        "PublishArtifactRequest",
    )

    request = PublishArtifactRequest(
        artifact_ref={
            "artifact_id": "artifact-123",
            "content_hash": "sha256:abc123",
            "store": "ephemeral",
            "manifest_ref": "manifests/artifact-123.json",
        },
        release_version="1.2.3",
        idempotency_key="publish-idem-123",
        atomic_stage="stage_invisible",
    )

    assert _field(request, "artifact_ref")["artifact_id"] == "artifact-123"
    assert _field(request, "release_version") == "1.2.3"
    assert _field(request, "idempotency_key") == "publish-idem-123"
    assert _field(request, "atomic_stage") == "stage_invisible"

    required_fields = ("artifact_ref", "release_version", "idempotency_key", "atomic_stage")
    for missing_field in required_fields:
        payload = {
            "artifact_ref": {
                "artifact_id": "artifact-123",
                "content_hash": "sha256:abc123",
                "store": "ephemeral",
                "manifest_ref": "manifests/artifact-123.json",
            },
            "release_version": "1.2.3",
            "idempotency_key": "publish-idem-123",
            "atomic_stage": "stage_invisible",
        }
        payload.pop(missing_field)
        with pytest.raises((TypeError, ValueError)):
            PublishArtifactRequest(**payload)


def test_golden_headless_request_only_accepts_run_results_ref_and_baseline_ref() -> None:
    GoldenHeadlessRequest = _load_symbol(
        "app.services.golden_headless",
        "GoldenHeadlessRequest",
    )

    request = GoldenHeadlessRequest(
        run_results_ref="runs/run-123/result.json",
        baseline_ref="golden/baseline-123/result.json",
    )

    assert _field(request, "run_results_ref") == "runs/run-123/result.json"
    assert _field(request, "baseline_ref") == "golden/baseline-123/result.json"
    assert "final_state" not in _field_names(request)
    assert "skill_id" not in _field_names(request)

    with pytest.raises((TypeError, ValueError)):
        GoldenHeadlessRequest(
            run_results_ref="runs/run-123/result.json",
            baseline_ref="golden/baseline-123/result.json",
            final_state={"legacy": "whole-run-diff"},
        )

    with pytest.raises((TypeError, ValueError)):
        GoldenHeadlessRequest(
            final_state={"legacy": "whole-run-diff"},
            baseline_ref="golden/baseline-123/result.json",
        )


def _load_symbol(module_name: str, symbol_name: str) -> Any:
    try:
        module = importlib.import_module(module_name)
    except ModuleNotFoundError as exc:
        pytest.fail(f"{module_name} is missing for the Studio MVP1 publish/golden contract: {exc}")
    try:
        return getattr(module, symbol_name)
    except AttributeError:
        pytest.fail(f"{module_name}.{symbol_name} is missing from the Studio MVP1 publish/golden contract")


def _field(value: Any, key: str) -> Any:
    if isinstance(value, dict):
        return value[key]
    return getattr(value, key)


def _field_names(value: Any) -> set[str]:
    if isinstance(value, dict):
        return set(value)
    model_fields = getattr(value, "model_fields", None)
    if isinstance(model_fields, dict):
        return set(model_fields)
    dataclass_fields = getattr(value, "__dataclass_fields__", None)
    if isinstance(dataclass_fields, dict):
        return set(dataclass_fields)
    return set(vars(value))
