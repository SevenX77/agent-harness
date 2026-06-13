from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest

SCHEMA_VERSION = "studio.mvp1.v1"


@pytest.mark.parametrize(
    ("injector_name", "error_code"),
    (
        ("inject_timeout", "transport.timeout"),
        ("inject_connection_refused", "transport.connection_refused"),
        ("inject_5xx", "transport.http_5xx"),
        ("inject_malformed_json", "transport.serialization_failed"),
        ("inject_missing_dto_fields", "transport.serialization_failed"),
        ("inject_schema_mismatch", "transport.schema_mismatch"),
    ),
)
def test_loopback_harness_injects_transport_failure_family(
    injector_name: str,
    error_code: str,
) -> None:
    HttpLoopbackHarness = _load_harness_symbol("HttpLoopbackHarness")

    with HttpLoopbackHarness(schema_version=SCHEMA_VERSION) as harness:
        harness.route(
            "/engine/run_artifact",
            data={"run_id": "run-123"},
            required_fields=("artifact_ref",),
        )
        getattr(harness, injector_name)("/engine/run_artifact")

        transport = harness.http_transport(schema_version=SCHEMA_VERSION)

        with pytest.raises(Exception) as exc_info:
            transport.post(
                "/engine/run_artifact",
                {"artifact_ref": {"artifact_id": "artifact-123"}},
                idempotency_key="idem-run-123",
            )

    assert _error_code(exc_info.value) == error_code


def test_loopback_harness_can_start_two_workers_with_shared_storage(tmp_path: Path) -> None:
    HttpLoopbackHarness = _load_harness_symbol("HttpLoopbackHarness")

    with HttpLoopbackHarness(schema_version=SCHEMA_VERSION, storage_root=tmp_path) as harness:
        worker_a, worker_b = harness.start_workers(count=2)

        created = worker_a.gateway_config_store.put_config(
            user_id="alice",
            key="llm.roles",
            value={"roles": {"writer": {}}},
        )
        from_other_worker = worker_b.gateway_config_store.get_config(
            user_id="alice",
            key="llm.roles",
        )

    assert _field(from_other_worker, "etag") == _etag(created)
    assert _field(from_other_worker, "value") == {"roles": {"writer": {}}}


def _load_harness_symbol(symbol_name: str) -> Any:
    harness_path = Path(__file__).resolve().parents[2] / "support" / "http_loopback_harness.py"
    if not harness_path.exists():
        pytest.fail(f"{harness_path} is missing for the Studio MVP1 HTTP loopback harness contract")
    spec = importlib.util.spec_from_file_location("studio_tests_http_loopback_harness", harness_path)
    if spec is None or spec.loader is None:
        pytest.fail(f"Unable to load Studio HTTP loopback harness from {harness_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    try:
        return getattr(module, symbol_name)
    except AttributeError:
        pytest.fail(f"{harness_path}:{symbol_name} is missing from the Studio MVP1 harness contract")


def _field(value: Any, key: str) -> Any:
    if isinstance(value, dict):
        return value[key]
    return getattr(value, key)


def _etag(value: Any) -> str:
    if isinstance(value, str):
        return value
    return str(_field(value, "etag"))


def _error_code(exc: BaseException) -> str | None:
    return getattr(exc, "error_code", None) or getattr(exc, "code", None)
