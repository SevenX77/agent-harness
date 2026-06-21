from __future__ import annotations

import ast
import builtins
import importlib
import inspect
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from graph_agent.core.adapter_contracts import RunArtifactRequest
from graph_agent.core.artifacts import ArtifactRef
from graph_agent.core.llm_provider import (
    FakeLLMProvider,
    LLMProviderError,
    LLMProviderRequest,
    LLMProviderResponse,
)
from graph_agent.core.phase_executor import PhaseExecutor
from graph_agent.core.state import BusinessData, FrameworkState, WorkflowState
from graph_agent.core.types import Phase


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


def test_engine_source_has_no_gateway_concrete_imports() -> None:
    source_root = Path(__file__).parents[2] / "src" / "graph_agent"
    offenders: list[str] = []

    for path in source_root.rglob("*.py"):
        module = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(module):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("graph_agent_gateway"):
                        offenders.append(f"{path.relative_to(source_root)}:{node.lineno}:{alias.name}")
            elif isinstance(node, ast.ImportFrom):
                module_name = node.module or ""
                if module_name.startswith("graph_agent_gateway"):
                    offenders.append(f"{path.relative_to(source_root)}:{node.lineno}:{module_name}")

    assert offenders == []


def test_llm_phase_uses_engine_owned_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    from graph_agent.core.phase_nodes import llm_phase_node as llm_phase_node_module

    provider = FakeLLMProvider(
        LLMProviderResponse(
            content="provider-driven phase output",
            metadata={"model_name": "fake-provider-model"},
        )
    )
    captured: dict[str, Any] = {}

    class _Agent:
        def __init__(self, model: Any) -> None:
            self.model = model

        def invoke(self, input: object, *, config: object) -> dict[str, list[Any]]:
            del config
            messages = input["messages"] if isinstance(input, dict) else []
            chat_result = self.model._generate(list(messages))
            return {"messages": [chat_result.generations[0].message]}

    def fake_create_agent(**kwargs: Any) -> _Agent:
        captured["model"] = kwargs["model"]
        return _Agent(kwargs["model"])

    monkeypatch.setattr(llm_phase_node_module, "create_custom_middlewares", lambda **_kwargs: [])
    monkeypatch.setattr(llm_phase_node_module, "create_agent", fake_create_agent)

    phase = Phase(name="draft", max_iterations=1, max_nudges=0, tier="writer")
    state: WorkflowState = {
        "data": BusinessData(topic="provider"),
        "flow": FrameworkState(thread_id="thread-d4"),
        "messages": [],
    }
    executor = PhaseExecutor(
        [],
        llm_provider=provider,
        save_compaction_sidecar=lambda **_kwargs: "sidecar",
    )

    result = executor.execute_llm_phase(phase, state)

    assert provider.requests
    assert provider.requests[0].role == "writer"
    assert provider.requests[0].metadata["phase_name"] == "draft"
    assert result["flow"].last_output == "provider-driven phase output"
    assert captured["model"].model_name == "fake-provider-model"


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


def test_provider_failure_payload_redacts_secret_and_traceback_details() -> None:
    runner = importlib.import_module("graph_agent.core.runner")
    provider_error = LLMProviderError(
        error_code="llm.provider_invoke_failed",
        message="provider exploded sk-live-secret Traceback (most recent call last)",
        retryable=True,
        details={
            "provider": "fake",
            "api_key": "sk-secret",
            "traceback": "Traceback ...",
            "nested_secret_hint": "secret",
            "provider_message": "upstream leaked sk-live-secret Traceback (most recent call last)",
        },
    )

    def failing_executor(_request: RunArtifactRequest) -> dict[str, Any]:
        raise provider_error

    result = runner.run_artifact(_request(), artifact_executor=failing_executor)

    assert result.error_code == "llm.provider_invoke_failed"
    assert result.retryable is True
    assert result.error_payload["retryable"] is True
    assert result.error_payload["message"] == "Provider invocation failed"
    assert result.error_payload["details"] == {
        "provider": "fake",
        "provider_message": "[redacted]",
    }
    dumped = json.dumps(result.error_payload, sort_keys=True)
    assert "sk-live-secret" not in dumped
    assert "Traceback" not in dumped


def test_run_artifact_source_has_no_single_llm_placeholder_helper() -> None:
    runner = importlib.import_module("graph_agent.core.runner")

    source = inspect.getsource(runner)

    assert "_invoke_llm_provider_helper" not in source
    assert "LLMProviderRequest(" not in source


def test_resume_skill_accepts_provider_spi_and_forwards_to_assembler(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    mock_skill_resolver: object,
) -> None:
    runner = importlib.import_module("graph_agent.core.runner")
    provider = FakeLLMProvider(
        LLMProviderResponse(
            content="resume provider output",
            metadata={"model_name": "resume-provider"},
        )
    )
    legacy_model_resolver = object()
    compiled = object()
    captured: dict[str, Any] = {}

    class _Graph:
        def invoke(self, _input: object, *, config: dict[str, Any]) -> dict[str, Any]:
            captured["invoke_config"] = config
            return {}

    def fake_assemble_graph(*_args: object, **kwargs: Any) -> object:
        captured["llm_provider"] = kwargs.get("llm_provider")
        captured["model_resolver"] = kwargs.get("model_resolver")
        captured["skill_resolver"] = kwargs.get("skill_resolver")
        return SimpleNamespace(graph=_Graph())

    monkeypatch.setattr(runner, "compile_skill", lambda *_args, **_kwargs: compiled)
    monkeypatch.setattr(runner, "assemble_graph", fake_assemble_graph)
    monkeypatch.setattr(runner, "_resolve_resume_checkpointer", lambda: object())
    monkeypatch.setattr(
        runner,
        "_resolve_resume_config",
        lambda *_args, **_kwargs: {"configurable": {"thread_id": "resume-d4"}},
    )
    monkeypatch.setattr(
        runner,
        "_apply_resume_context_overrides",
        lambda _graph, _compiled, config, _overrides, **_kwargs: config,
    )
    monkeypatch.setattr(
        runner,
        "_apply_resume_human_response",
        lambda _graph, config, _response: config,
    )
    monkeypatch.setattr(
        runner,
        "_finalize_successful_v030_run",
        lambda *_args, **_kwargs: {"resumed": True},
    )

    result = runner.resume_skill(
        tmp_path / "SKILL.md",
        workspace_dir=tmp_path,
        run_id="resume-d4",
        skill_resolver=mock_skill_resolver,
        model_resolver=legacy_model_resolver,
        llm_provider=provider,
    )

    assert result.success is True
    assert captured["llm_provider"] is provider
    assert captured["model_resolver"] is legacy_model_resolver
    assert captured["skill_resolver"] is mock_skill_resolver
    assert captured["invoke_config"] == {"configurable": {"thread_id": "resume-d4"}}
