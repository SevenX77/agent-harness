"""An engine fatal that already named itself must not be flattened to "unexpected".

The engine's own fail-fast path builds a structured `ErrorPayload` — an
`[F-v3-*]` code, the phase it happened in, the offending field — and hangs it on
the exception (`GraphAgentError.__init__` sets `.payload` / `.error_payload` /
`.phase_id` / `.field_path`). `run_artifact`'s catch-all read `exc.error_code`
and `exc.details`, attributes that class does not have, so every one of those
fatals arrived at the caller as a bare `engine.unexpected_error` with nothing
but `exception_type`.

Observed live on 2026-08-15: a phase whose validator dropped a required field
surfaced in the desktop app as
`engine_error_code: "engine.unexpected_error"` /
`details: {"exception_type": "GraphAgentFatalError"}` — the code
`[F-v3-runtime-state-mapping-failed]` and the phase name were both raised and
both discarded, leaving no way to tell which of the schema's three checkpoints
had rejected the phase.
"""

from __future__ import annotations

import importlib
from typing import Any

from graph_agent.core.adapter_contracts import RunArtifactRequest
from graph_agent.core.artifacts import ArtifactRef
from graph_agent.core.exceptions import GraphAgentFatalError, make_error_payload


def _request(idempotency_key: str) -> RunArtifactRequest:
    return RunArtifactRequest(
        artifact_ref=ArtifactRef(
            artifact_id="artifact-fatal-payload",
            content_hash="sha256:fatal-payload",
            store="ephemeral",
            manifest_ref="object://manifest.json",
            source_map_ref="object://source-map.json",
        ),
        inputs={"topic": "fatal"},
        execution_context={"workspace_id": "local"},
        idempotency_key=idempotency_key,
    )


def _fatal(_: RunArtifactRequest) -> dict[str, Any]:
    detail = "phase output schema validation failed: 'raw_settings_markdown' is a required property"
    raise GraphAgentFatalError(
        detail,
        payload=make_error_payload(
            "[F-v3-runtime-state-mapping-failed]",
            detail,
            phase_id="settings",
            field_path="raw_settings_markdown",
        ),
    )


def test_a_fatal_keeps_the_code_it_raised_itself_with() -> None:
    runner = importlib.import_module("graph_agent.core.runner")

    result = runner.run_artifact(_request("idem-fatal-1"), artifact_executor=_fatal)

    assert result.error_code == "[F-v3-runtime-state-mapping-failed]", (
        "the engine classified this failure when it raised it; reporting "
        f"{result.error_code!r} throws that classification away"
    )
    assert result.error_payload["error_code"] == "[F-v3-runtime-state-mapping-failed]"


def test_a_fatal_keeps_where_it_happened() -> None:
    """The code alone does not locate it — the phase and field must survive too."""
    runner = importlib.import_module("graph_agent.core.runner")

    result = runner.run_artifact(_request("idem-fatal-2"), artifact_executor=_fatal)

    details = result.error_payload["details"]
    assert details["phase_id"] == "settings"
    assert details["field_path"] == "raw_settings_markdown"
    assert details["exception_type"] == "GraphAgentFatalError"


def test_an_exception_with_no_payload_still_reads_unclassified() -> None:
    """The fallback must stay in place for exceptions that never named themselves."""
    runner = importlib.import_module("graph_agent.core.runner")

    def _bare(_: RunArtifactRequest) -> dict[str, Any]:
        raise RuntimeError("something the engine cannot classify")

    result = runner.run_artifact(_request("idem-fatal-3"), artifact_executor=_bare)

    assert result.error_code == "engine.unexpected_error"
