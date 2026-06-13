from __future__ import annotations

import builtins
import importlib
import inspect
from typing import Any

import pytest

from graph_agent.core.adapter_contracts import RunArtifactRequest
from graph_agent.core.artifacts import ArtifactRef
from graph_agent.core.llm_provider import LLMProviderError, LLMProviderRequest, LLMProviderResponse


class FailingLLMProvider:
    def __init__(self, error: LLMProviderError) -> None:
        self.error = error
        self.requests: list[LLMProviderRequest] = []

    def invoke(self, request: LLMProviderRequest) -> LLMProviderResponse:
        self.requests.append(request)
        raise self.error


def _artifact_ref() -> ArtifactRef:
    return ArtifactRef(
        artifact_id="artifact-spi-demo",
        content_hash="sha256:spi-demo",
        store="ephemeral",
        manifest_ref="object://manifest.json",
        source_map_ref="object://source-map.json",
    )


def _request() -> RunArtifactRequest:
    return RunArtifactRequest(
        artifact_ref=_artifact_ref(),
        inputs={"topic": "red"},
        execution_context={"workspace_id": "local"},
        idempotency_key="idem-spi",
    )


def test_importing_graph_agent_does_not_require_gateway_concrete_module(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_import = builtins.__import__

    def guarded_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name.startswith("graph_agent_gateway"):
            raise AssertionError(f"graph_agent import must not import {name}")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)

    importlib.import_module("graph_agent")


def test_run_artifact_without_materialized_artifact_fails_with_explicit_error() -> None:
    runner = importlib.import_module("graph_agent.core.runner")

    result = runner.run_artifact(_request(), llm_provider=None)

    assert result.error_code == "runtime.artifact_not_materialized"
    assert result.error_payload["error_code"] == "runtime.artifact_not_materialized"
    assert result.error_payload["details"]["content_hash"] == "sha256:spi-demo"


def test_run_artifact_does_not_fallback_to_single_llm_provider_call() -> None:
    runner = importlib.import_module("graph_agent.core.runner")
    provider = FailingLLMProvider(
        LLMProviderError(
            error_code="llm.provider_invoke_failed",
            message="provider exploded",
            retryable=False,
            details={"provider": "fake"},
        )
    )

    result = runner.run_artifact(_request(), llm_provider=provider)

    assert provider.requests == []
    assert result.error_code == "runtime.artifact_not_materialized"


def test_artifact_executor_provider_failure_uses_spi_error_shape() -> None:
    runner = importlib.import_module("graph_agent.core.runner")
    provider_error = LLMProviderError(
        error_code="llm.provider_invoke_failed",
        message="provider exploded",
        retryable=False,
        details={"provider": "fake"},
    )

    def failing_executor(_request: RunArtifactRequest) -> dict[str, Any]:
        raise provider_error

    result = runner.run_artifact(_request(), artifact_executor=failing_executor)

    assert result.error_code == "llm.provider_invoke_failed"
    assert result.error_payload["details"] == {"provider": "fake"}


def test_run_artifact_source_has_no_single_llm_placeholder_helper() -> None:
    runner = importlib.import_module("graph_agent.core.runner")

    source = inspect.getsource(runner)

    assert "_invoke_llm_provider_helper" not in source
    assert "LLMProviderRequest(" not in source
