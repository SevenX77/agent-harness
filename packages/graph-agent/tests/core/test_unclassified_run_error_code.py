"""An engine failure the engine cannot classify must not be labelled an LLM error.

`run_artifact` wraps the execution of the WHOLE graph. Its `except Exception`
defaulted the error code to `llm.provider_invoke_failed`, so a KeyError in the
assembler, a RuntimeError from asyncio, or any other internal fault was reported
to the caller as "the LLM provider invocation failed" — a confident, specific,
wrong attribution that sends whoever reads it into the gateway.

The default can only ever be wrong: every genuine provider failure already
carries its own code. `LLMProviderError.__init__` takes `error_code` as a
required argument and `LLMProviderMissingError` sets it at class level
(`core/llm_provider.py`), so `getattr(exc, "error_code", ...)` never falls back
for them. The fallback fires exclusively for exceptions that are NOT provider
errors.

Observed live on 2026-08-15: clicking Predict in the desktop app surfaced
`asyncio.run() cannot be called from a running event loop` under
`engine_error_code: "llm.provider_invoke_failed"`.
"""

from __future__ import annotations

import importlib
from typing import Any

from graph_agent.core.adapter_contracts import RunArtifactRequest
from graph_agent.core.artifacts import ArtifactRef


def _artifact_ref() -> ArtifactRef:
    return ArtifactRef(
        artifact_id="artifact-unclassified-error",
        content_hash="sha256:unclassified-error",
        store="ephemeral",
        manifest_ref="object://manifest.json",
        source_map_ref="object://source-map.json",
    )


def _request(idempotency_key: str) -> RunArtifactRequest:
    return RunArtifactRequest(
        artifact_ref=_artifact_ref(),
        inputs={"topic": "unclassified"},
        execution_context={"workspace_id": "local"},
        idempotency_key=idempotency_key,
    )


def _explode(_: RunArtifactRequest) -> dict[str, Any]:
    raise RuntimeError("asyncio.run() cannot be called from a running event loop")


def test_an_engine_fault_is_not_reported_as_a_provider_failure() -> None:
    runner = importlib.import_module("graph_agent.core.runner")

    result = runner.run_artifact(_request("idem-unclassified-1"), artifact_executor=_explode)

    assert result.error_code == "engine.unexpected_error", (
        "an exception with no error_code of its own is by definition not a provider "
        f"error, but it was labelled {result.error_code!r}"
    )
    assert result.error_payload["error_code"] == "engine.unexpected_error"


def test_an_unclassified_fault_keeps_what_actually_happened() -> None:
    """Relabelling is only half the fix — the payload has to say what went wrong."""
    runner = importlib.import_module("graph_agent.core.runner")

    result = runner.run_artifact(_request("idem-unclassified-2"), artifact_executor=_explode)

    assert "asyncio.run()" in result.error_payload["message"]
    assert result.error_payload["details"]["exception_type"] == "RuntimeError"
    assert result.error_payload["retryable"] is False


def test_a_provider_failure_keeps_its_own_code() -> None:
    """The relabelling must not swallow codes the exception carries itself."""
    runner = importlib.import_module("graph_agent.core.runner")
    from graph_agent.core.llm_provider import LLMProviderError

    def _provider_boom(_: RunArtifactRequest) -> dict[str, Any]:
        raise LLMProviderError(
            error_code="llm.provider_invoke_failed",
            message="upstream said no",
            retryable=True,
            details={"status": 503},
        )

    result = runner.run_artifact(_request("idem-unclassified-3"), artifact_executor=_provider_boom)

    assert result.error_code == "llm.provider_invoke_failed"
    assert result.retryable is True
